"""
Query Router для классификации запросов.

Определяет нужен ли агент с инструментами или можно ответить напрямую через LLM.
Использует двухуровневую стратегию:
1. Быстрая эвристика по ключевым словам
2. LLM классификация при неопределенности
"""

import logging
import json
from typing import Optional
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate

from .models import RouteDecision, RouteType

logger = logging.getLogger(__name__)


# ============================================================================
# ROUTER PROMPT
# ============================================================================

ROUTER_PROMPT = """Определи тип запроса пользователя для системы Travel Agent.

ТИПЫ ЗАПРОСОВ:

1. "simple" - ПРОСТОЙ ВОПРОС, можно ответить сразу без инструментов:
   - Вопросы "что такое", "кто такой", "какая столица"
   - Общие вопросы о путешествиях без конкретных действий
   - Объяснения терминов (виза, паспорт, транзит)
   - Математические вычисления
   - Общая информация без поиска в реальном времени

   Примеры SIMPLE:
   - "Что такое шенгенская виза?"
   - "Какая столица Франции?"
   - "Сколько часов лететь до Парижа из Москвы?"
   - "Объясни что такое транзитная виза"
   - "Расскажи про культуру Японии"

2. "agent" - ТРЕБУЕТСЯ АГЕНТ (поиск, планирование, использование инструментов):
   - Поиск рейсов, отелей
   - Проверка погоды в реальном времени
   - Планирование поездок
   - Сравнение вариантов
   - Любые действия требующие актуальных данных

   Примеры AGENT:
   - "Найди рейсы из Москвы в Париж"
   - "Какая погода в Берлине?"
   - "Спланируй поездку в Токио"
   - "Подбери рейсы на выходные"
   - "Сравни погоду в Милане и Риме"

ВАЖНО:
- При сомнении выбирай "agent" (лучше перестраховаться)
- Если упоминается конкретный город для погоды → "agent"
- Если нужны актуальные данные → "agent"
- Confidence < 0.7 → обязательно "agent"

ЗАПРОС ПОЛЬЗОВАТЕЛЯ:
{query}

ВЕРНИ ТОЛЬКО JSON (без markdown, без комментариев):
{{
    "type": "simple" | "agent",
    "confidence": 0.0-1.0,
    "reasoning": "краткое объяснение решения (1-2 предложения)",
    "direct_answer": "ответ на simple вопрос если type=simple, иначе null"
}}
"""


# ============================================================================
# QUERY ROUTER
# ============================================================================

class QueryRouter:
    """
    Маршрутизатор запросов для Travel Agent.

    Классифицирует запросы на:
    - SIMPLE: можно ответить напрямую
    - AGENT: нужен агент с инструментами

    Использует двухуровневую стратегию:
    1. Быстрая эвристика (паттерны ключевых слов)
    2. LLM классификация при неопределенности
    """

    # Паттерны для быстрой классификации
    SIMPLE_PATTERNS = [
        "что такое",
        "кто такой",
        "кто такая",
        "какая столица",
        "какой столица",
        "сколько будет",
        "объясни",
        "расскажи про",
        "расскажи о",
        "что значит",
        "как понять",
        "определение",
        "разница между",
    ]

    AGENT_PATTERNS = [
        "найди",
        "найти",
        "спланируй",
        "спланировать",
        "подбери",
        "подобрать",
        "забронируй",
        "забронировать",
        "сравни",
        "сравнить",
        "покажи рейсы",
        "рейсы из",
        "рейсы в",
        "какая погода",
        "погода в",
        "поиск рейсов",
        "поездку в",
        "поездка в",
    ]

    def __init__(
        self,
        llm: ChatOpenAI,
        use_heuristics: bool = True,
        confidence_threshold: float = 0.7
    ):
        """
        Initialize router.

        Args:
            llm: Language model for classification
            use_heuristics: Use fast keyword heuristics before LLM
            confidence_threshold: Minimum confidence for simple route (< threshold → agent)
        """
        self.llm = llm
        self.use_heuristics = use_heuristics
        self.confidence_threshold = confidence_threshold

        # Создаём prompt template
        self.prompt = ChatPromptTemplate.from_template(ROUTER_PROMPT)

        logger.info(
            f"QueryRouter initialized (heuristics={use_heuristics}, "
            f"threshold={confidence_threshold})"
        )

    def _heuristic_classification(self, query: str) -> Optional[RouteDecision]:
        """
        Быстрая эвристическая классификация по ключевым словам.

        Args:
            query: Запрос пользователя

        Returns:
            RouteDecision если уверены, None если нужна LLM классификация
        """
        query_lower = query.lower().strip()

        # Проверяем AGENT паттерны (более специфичные, проверяем первыми)
        for pattern in self.AGENT_PATTERNS:
            if pattern in query_lower:
                logger.info(f"Heuristic: AGENT (matched pattern: '{pattern}')")
                return RouteDecision(
                    route_type=RouteType.AGENT,
                    confidence=0.85,
                    reasoning=f"Запрос содержит паттерн '{pattern}' - требуется агент",
                    direct_answer=None
                )

        # Проверяем SIMPLE паттерны
        for pattern in self.SIMPLE_PATTERNS:
            if pattern in query_lower:
                logger.info(f"Heuristic: SIMPLE (matched pattern: '{pattern}')")
                # Для simple возвращаем None - пусть LLM даст прямой ответ
                return RouteDecision(
                    route_type=RouteType.SIMPLE,
                    confidence=0.8,
                    reasoning=f"Запрос содержит паттерн '{pattern}' - простой вопрос",
                    direct_answer=None  # LLM даст ответ
                )

        # Эвристика не уверена
        logger.info("Heuristic: uncertain, falling back to LLM")
        return None

    async def _llm_classification(self, query: str) -> RouteDecision:
        """
        LLM-based классификация запроса.

        Args:
            query: Запрос пользователя

        Returns:
            RouteDecision с результатом классификации
        """
        logger.info("Using LLM for query classification")

        try:
            # Форматируем prompt
            messages = self.prompt.format_messages(query=query)

            # Вызываем LLM
            response = await self.llm.ainvoke(messages)
            response_text = response.content.strip()

            # Парсим JSON ответ
            # Удаляем markdown если есть
            if response_text.startswith("```"):
                # Убираем ```json и ```
                lines = response_text.split("\n")
                response_text = "\n".join(
                    line for line in lines
                    if not line.strip().startswith("```")
                )

            result_dict = json.loads(response_text)

            # Создаём RouteDecision
            decision = RouteDecision(
                route_type=RouteType(result_dict["type"]),
                confidence=float(result_dict["confidence"]),
                reasoning=result_dict["reasoning"],
                direct_answer=result_dict.get("direct_answer")
            )

            logger.info(
                f"LLM classification: {decision.route_type} "
                f"(confidence={decision.confidence:.2f})"
            )

            return decision

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response: {response_text[:200]}")
            logger.error(f"JSON error: {e}")

            # Fallback - считаем что нужен агент
            return RouteDecision(
                route_type=RouteType.AGENT,
                confidence=0.5,
                reasoning="Не удалось распарсить ответ LLM, используем agent как fallback",
                direct_answer=None
            )

        except Exception as e:
            logger.error(f"Error in LLM classification: {e}", exc_info=True)

            # Fallback - используем агент
            return RouteDecision(
                route_type=RouteType.AGENT,
                confidence=0.5,
                reasoning=f"Ошибка классификации: {str(e)}, используем agent как fallback",
                direct_answer=None
            )

    async def route(self, query: str) -> RouteDecision:
        """
        Классифицировать запрос пользователя.

        Алгоритм:
        1. Пробуем быструю эвристику (если enabled)
        2. Если эвристика не уверена → LLM классификация
        3. Если confidence < threshold → route to agent (безопаснее)
        4. Если simple route но нет direct_answer → LLM для ответа

        Args:
            query: Запрос пользователя

        Returns:
            RouteDecision с типом маршрута и параметрами
        """
        logger.info(f"Routing query: {query[:100]}")

        decision = None

        # 1. Пробуем эвристику
        if self.use_heuristics:
            decision = self._heuristic_classification(query)

        # 2. Если эвристика не уверена → LLM
        if decision is None:
            decision = await self._llm_classification(query)

        # 3. Проверяем confidence threshold
        if decision.confidence < self.confidence_threshold:
            logger.warning(
                f"Low confidence ({decision.confidence:.2f} < {self.confidence_threshold}), "
                "routing to agent as fallback"
            )
            decision = RouteDecision(
                route_type=RouteType.AGENT,
                confidence=decision.confidence,
                reasoning=f"Низкая уверенность ({decision.confidence:.2f}), используем agent",
                direct_answer=None
            )

        # 4. Если simple route без прямого ответа → получаем ответ от LLM
        if decision.route_type == RouteType.SIMPLE and decision.direct_answer is None:
            logger.info("Simple route without direct answer, getting LLM response")

            try:
                # Простой запрос к LLM для ответа
                simple_prompt = ChatPromptTemplate.from_template(
                    "Ты - помощник по путешествиям. Ответь на вопрос пользователя кратко и понятно.\n\n"
                    "Вопрос: {query}\n\n"
                    "Ответ:"
                )
                messages = simple_prompt.format_messages(query=query)
                response = await self.llm.ainvoke(messages)

                decision.direct_answer = response.content.strip()
                logger.info(f"Got direct answer ({len(decision.direct_answer)} chars)")

            except Exception as e:
                logger.error(f"Failed to get direct answer: {e}")
                # Fallback - route to agent
                decision = RouteDecision(
                    route_type=RouteType.AGENT,
                    confidence=0.5,
                    reasoning=f"Не удалось получить прямой ответ: {str(e)}",
                    direct_answer=None
                )

        logger.info(
            f"Final routing decision: {decision.route_type} "
            f"(confidence={decision.confidence:.2f})"
        )

        return decision


# ============================================================================
# TESTS
# ============================================================================

if __name__ == "__main__":
    """Тестирование router."""
    import asyncio
    import os
    from dotenv import load_dotenv

    load_dotenv()

    async def test_router():
        """Test query router"""
        print("Testing Query Router...\n")

        # Инициализируем LLM
        llm = ChatOpenAI(
            model="gpt-4o-mini",
            temperature=0.0,
            api_key=os.getenv("OPENAI_API_KEY")
        )

        router = QueryRouter(llm)

        # Тестовые запросы
        test_queries = [
            # SIMPLE queries
            "Что такое шенгенская виза?",
            "Какая столица Франции?",
            "Расскажи про культуру Японии",

            # AGENT queries
            "Найди рейсы из Москвы в Париж",
            "Какая погода в Берлине?",
            "Спланируй поездку в Токио на выходные",

            # Ambiguous (should use LLM)
            "Хочу в Париж",
            "Берлин интересный город?",
        ]

        for i, query in enumerate(test_queries, 1):
            print(f"\n{'='*60}")
            print(f"Test {i}: {query}")
            print('='*60)

            decision = await router.route(query)

            print(f"Route: {decision.route_type}")
            print(f"Confidence: {decision.confidence:.2f}")
            print(f"Reasoning: {decision.reasoning}")
            if decision.direct_answer:
                print(f"Direct Answer: {decision.direct_answer[:200]}...")

    # Run tests
    asyncio.run(test_router())
