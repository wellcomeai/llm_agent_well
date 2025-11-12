"""
Task Planner для создания структурированных планов выполнения.

Анализирует запрос пользователя и создаёт план с шагами (DAG).
Определяет какие инструменты использовать, параметры, зависимости между шагами.
Оптимизирует план для параллельного выполнения где возможно.
"""

import logging
import json
from typing import List, Dict, Any, Optional
from datetime import datetime
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from langchain.tools import BaseTool

from .models import Plan, Step

logger = logging.getLogger(__name__)


# ============================================================================
# PLANNER PROMPT
# ============================================================================

PLANNER_PROMPT = """Ты - опытный планировщик задач для Travel Agent системы.
Твоя задача - создать детальный структурированный план выполнения запроса пользователя.

ДОСТУПНЫЕ ИНСТРУМЕНТЫ:
{tools_description}

ЗАПРОС ПОЛЬЗОВАТЕЛЯ:
{query}

КОНТЕКСТ (история диалога):
{context}

ИНСТРУКЦИИ ПО СОЗДАНИЮ ПЛАНА:

1. **Анализ запроса:**
   - Определи что хочет пользователь
   - Извлеки сущности (города, даты, etc.)
   - Определи какие данные уже есть, каких не хватает

2. **Создание шагов:**
   - Разбей задачу на атомарные шаги
   - Каждый шаг = один вызов инструмента или действие
   - Шаги должны быть независимыми где возможно
   - ID шагов начинаются с 1

3. **Типы шагов:**
   - `get_weather` - проверить погоду (параметр: city)
   - `search_flights` - найти рейсы (параметры: from_city, to_city, date)
   - `ask_user` - спросить у пользователя недостающую информацию (параметр: questions)
   - `synthesize_response` - сформировать финальный ответ (параметр: data_from)

4. **Правила:**
   - Погоду проверяй для города НАЗНАЧЕНИЯ (to_city), не вылета
   - Если нет города вылета → создай шаг `ask_user` (НЕ search_flights!)
   - Если нет даты → используй "завтра" как default или спроси
   - Независимые шаги должны иметь `can_parallel: true`
   - Зависимые шаги указывай в `depends_on`

5. **Оптимизация:**
   - Погода и рейсы могут выполняться параллельно (depends_on: [])
   - Финальный синтез зависит от всех предыдущих шагов
   - Минимизируй общее время выполнения

6. **Оценка времени:**
   - get_weather: 3 секунды
   - search_flights: 5 секунд
   - ask_user: 0 секунд (immediate)
   - synthesize_response: 2 секунды

ПРИМЕРЫ:

**Пример 1 - Полная информация:**
Запрос: "Найди рейсы из Москвы в Париж на 20 января"

План:
{{
  "goal": "Найти рейсы Москва→Париж на 20 января и проверить погоду",
  "steps": [
    {{
      "id": 1,
      "action": "get_weather",
      "params": {{"city": "Paris"}},
      "depends_on": [],
      "can_parallel": true,
      "description": "Проверить погоду в Париже",
      "estimated_time_sec": 3
    }},
    {{
      "id": 2,
      "action": "search_flights",
      "params": {{"from_city": "Moscow", "to_city": "Paris", "date": "2025-01-20"}},
      "depends_on": [],
      "can_parallel": true,
      "description": "Найти рейсы Москва→Париж на 20 января",
      "estimated_time_sec": 5
    }},
    {{
      "id": 3,
      "action": "synthesize_response",
      "params": {{"data_from": [1, 2]}},
      "depends_on": [1, 2],
      "can_parallel": false,
      "description": "Сформировать итоговый ответ с рейсами и погодой",
      "estimated_time_sec": 2
    }}
  ],
  "total_estimated_time": 7,
  "metadata": {{
    "user_query": "Найди рейсы из Москвы в Париж на 20 января",
    "extracted_entities": {{
      "from_city": "Moscow",
      "to_city": "Paris",
      "date": "2025-01-20"
    }}
  }}
}}

**Пример 2 - Неполная информация (нет города вылета):**
Запрос: "Спланируй поездку в Берлин на выходные"

План:
{{
  "goal": "Спланировать поездку в Берлин: проверить погоду и запросить недостающую информацию",
  "steps": [
    {{
      "id": 1,
      "action": "get_weather",
      "params": {{"city": "Berlin"}},
      "depends_on": [],
      "can_parallel": true,
      "description": "Проверить погоду в Берлине",
      "estimated_time_sec": 3
    }},
    {{
      "id": 2,
      "action": "ask_user",
      "params": {{
        "questions": [
          "Из какого города вы планируете вылететь?",
          "Какие точно даты выходных? (например, 18-20 января)"
        ]
      }},
      "depends_on": [1],
      "can_parallel": false,
      "description": "Запросить у пользователя город вылета и точные даты",
      "estimated_time_sec": 0
    }}
  ],
  "total_estimated_time": 3,
  "metadata": {{
    "user_query": "Спланируй поездку в Берлин на выходные",
    "missing_info": ["from_city", "exact_dates"]
  }}
}}

**Пример 3 - Только погода:**
Запрос: "Какая погода в Токио?"

План:
{{
  "goal": "Проверить погоду в Токио",
  "steps": [
    {{
      "id": 1,
      "action": "get_weather",
      "params": {{"city": "Tokyo"}},
      "depends_on": [],
      "can_parallel": true,
      "description": "Проверить текущую погоду в Токио",
      "estimated_time_sec": 3
    }},
    {{
      "id": 2,
      "action": "synthesize_response",
      "params": {{"data_from": [1]}},
      "depends_on": [1],
      "can_parallel": false,
      "description": "Сформировать ответ о погоде",
      "estimated_time_sec": 2
    }}
  ],
  "total_estimated_time": 5,
  "metadata": {{
    "user_query": "Какая погода в Токио?",
    "query_type": "weather_only"
  }}
}}

ТЕПЕРЬ СОЗДАЙ ПЛАН ДЛЯ ЗАПРОСА ПОЛЬЗОВАТЕЛЯ.

ВАЖНО: Верни ТОЛЬКО валидный JSON объект плана (без markdown блоков, без комментариев).
JSON должен точно соответствовать структуре Plan из примеров выше.
"""


# ============================================================================
# TASK PLANNER
# ============================================================================

class TaskPlanner:
    """
    Планировщик задач для Travel Agent.

    Создаёт структурированные планы выполнения (DAG) на основе:
    - Запроса пользователя
    - Доступных инструментов
    - Контекста диалога

    Оптимизирует план для параллельного выполнения.
    """

    def __init__(
        self,
        llm: ChatOpenAI,
        tools: Optional[List[BaseTool]] = None
    ):
        """
        Initialize task planner.

        Args:
            llm: Language model for planning
            tools: Available tools (optional, can be set later)
        """
        self.llm = llm
        self.tools = tools or []

        self.prompt = ChatPromptTemplate.from_template(PLANNER_PROMPT)

        logger.info(f"TaskPlanner initialized with {len(self.tools)} tools")

    def set_tools(self, tools: List[BaseTool]):
        """Update available tools."""
        self.tools = tools
        logger.info(f"Tools updated: {len(self.tools)} tools available")

    def _format_tools_description(self) -> str:
        """
        Форматирует описание доступных инструментов для промпта.

        Returns:
            Строка с описанием инструментов
        """
        if not self.tools:
            return "Нет доступных инструментов"

        descriptions = []
        for i, tool in enumerate(self.tools, 1):
            desc = f"{i}. **{tool.name}**"
            if hasattr(tool, 'description') and tool.description:
                desc += f"\n   Описание: {tool.description}"
            descriptions.append(desc)

        # Добавляем виртуальные инструменты
        descriptions.append(
            "\n3. **ask_user** (виртуальный инструмент)\n"
            "   Описание: Спросить у пользователя недостающую информацию\n"
            "   Параметры: questions (list of strings)"
        )
        descriptions.append(
            "\n4. **synthesize_response** (виртуальный инструмент)\n"
            "   Описание: Сформировать финальный ответ из собранных данных\n"
            "   Параметры: data_from (list of step IDs)"
        )

        return "\n".join(descriptions)

    def _extract_json_from_response(self, text: str) -> str:
        """
        Извлекает JSON из ответа LLM (удаляет markdown блоки если есть).

        Args:
            text: Текст ответа LLM

        Returns:
            Чистый JSON string
        """
        text = text.strip()

        # Удаляем markdown code blocks
        if text.startswith("```"):
            lines = text.split("\n")
            # Убираем первую строку ```json и последнюю ```
            text = "\n".join(
                line for line in lines[1:-1]
                if not line.strip() == "```"
            )

        # Если есть текст до { или после } - удаляем
        start = text.find("{")
        end = text.rfind("}") + 1

        if start != -1 and end > start:
            text = text[start:end]

        return text.strip()

    async def create_plan(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Plan:
        """
        Создать план выполнения для запроса.

        Args:
            query: Запрос пользователя
            context: Контекст диалога (опционально)

        Returns:
            Plan объект с шагами и зависимостями

        Raises:
            ValueError: Если не удалось создать валидный план
        """
        logger.info(f"Creating plan for query: {query[:100]}")

        # Подготавливаем контекст
        context_str = json.dumps(context or {}, ensure_ascii=False, indent=2)
        tools_desc = self._format_tools_description()

        try:
            # Форматируем prompt
            messages = self.prompt.format_messages(
                query=query,
                tools_description=tools_desc,
                context=context_str
            )

            # Вызываем LLM
            response = await self.llm.ainvoke(messages)
            response_text = response.content

            logger.debug(f"LLM response length: {len(response_text)} chars")

            # Извлекаем JSON
            json_text = self._extract_json_from_response(response_text)

            # Парсим JSON
            plan_dict = json.loads(json_text)

            # Создаём Plan объект (с Pydantic валидацией!)
            plan = Plan(**plan_dict)

            logger.info(
                f"Plan created successfully: {len(plan.steps)} steps, "
                f"estimated time: {plan.total_estimated_time}s"
            )

            # Логируем шаги
            for step in plan.steps:
                logger.debug(
                    f"  Step {step.id}: {step.action} "
                    f"(parallel={step.can_parallel}, deps={step.depends_on})"
                )

            return plan

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}")
            logger.error(f"Response text: {response_text[:500]}")

            # Fallback - создаём простой план с ask_user
            logger.warning("Creating fallback plan with ask_user step")
            return self._create_fallback_plan(query, "Не удалось распарсить план от LLM")

        except Exception as e:
            logger.error(f"Error creating plan: {e}", exc_info=True)

            # Fallback plan
            return self._create_fallback_plan(query, f"Ошибка создания плана: {str(e)}")

    def _create_fallback_plan(self, query: str, reason: str) -> Plan:
        """
        Создаёт fallback план когда основной механизм не сработал.

        Args:
            query: Исходный запрос
            reason: Причина fallback

        Returns:
            Простой Plan с ask_user шагом
        """
        logger.warning(f"Creating fallback plan: {reason}")

        return Plan(
            goal=f"Обработать запрос: {query[:100]}",
            steps=[
                Step(
                    id=1,
                    action="ask_user",
                    params={
                        "questions": [
                            f"Произошла ошибка при планировании ({reason}). "
                            f"Уточните, пожалуйста, ваш запрос: {query}"
                        ]
                    },
                    depends_on=[],
                    can_parallel=True,
                    description="Попросить пользователя уточнить запрос",
                    estimated_time_sec=0
                )
            ],
            total_estimated_time=0,
            metadata={
                "fallback": True,
                "reason": reason,
                "original_query": query
            }
        )


# ============================================================================
# TESTS
# ============================================================================

if __name__ == "__main__":
    """Тестирование planner."""
    import asyncio
    import os
    from dotenv import load_dotenv

    # Mock tools для тестирования
    from langchain.tools import Tool

    load_dotenv()

    async def test_planner():
        """Test task planner"""
        print("Testing Task Planner...\n")

        # Инициализируем LLM
        llm = ChatOpenAI(
            model="gpt-4o-mini",
            temperature=0.0,
            api_key=os.getenv("OPENAI_API_KEY")
        )

        # Mock tools
        tools = [
            Tool(
                name="get_weather",
                func=lambda city: f"Weather in {city}",
                description="Получает текущую погоду для указанного города"
            ),
            Tool(
                name="search_flights",
                func=lambda **kwargs: f"Flights: {kwargs}",
                description="Ищет рейсы между городами на указанную дату"
            )
        ]

        planner = TaskPlanner(llm, tools)

        # Тестовые запросы
        test_queries = [
            "Найди рейсы из Москвы в Париж на 20 января",
            "Спланируй поездку в Берлин на выходные",
            "Какая погода в Токио?",
        ]

        for i, query in enumerate(test_queries, 1):
            print(f"\n{'='*60}")
            print(f"Test {i}: {query}")
            print('='*60)

            try:
                plan = await planner.create_plan(query)

                print(f"\nGoal: {plan.goal}")
                print(f"Steps: {len(plan.steps)}")
                print(f"Estimated time: {plan.total_estimated_time}s")

                print("\nSteps:")
                for step in plan.steps:
                    print(f"  {step.id}. {step.description}")
                    print(f"     Action: {step.action}")
                    print(f"     Params: {step.params}")
                    print(f"     Depends on: {step.depends_on}")
                    print(f"     Can parallel: {step.can_parallel}")

            except Exception as e:
                print(f"❌ Error: {e}")

    # Run tests
    asyncio.run(test_planner())
