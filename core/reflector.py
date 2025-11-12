"""
Result Reflector для анализа результатов выполнения планов.

Проверяет:
- Все ли шаги выполнены успешно
- Ответили ли мы на исходный вопрос пользователя
- Нужна ли дополнительная информация
- Есть ли логические противоречия

Может предложить replan если результаты неполные.
"""

import logging
import json
from typing import Dict, Any, Optional
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate

try:
    from .models import Plan, ExecutionResult, ReflectionResult, ReflectionStatus
except ImportError:
    from models import Plan, ExecutionResult, ReflectionResult, ReflectionStatus

logger = logging.getLogger(__name__)


# ============================================================================
# REFLECTION PROMPT
# ============================================================================

REFLECTION_PROMPT = """Ты - эксперт по анализу результатов выполнения планов Travel Agent системы.
Твоя задача - проверить выполнен ли исходный запрос пользователя и нужны ли дополнительные действия.

ИСХОДНЫЙ ЗАПРОС ПОЛЬЗОВАТЕЛЯ:
{original_query}

ПЛАН КОТОРЫЙ БЫЛ ВЫПОЛНЕН:
Цель: {plan_goal}
Шаги:
{plan_steps}

РЕЗУЛЬТАТЫ ВЫПОЛНЕНИЯ:
{execution_results}

ОШИБКИ (если были):
{errors}

СТАТИСТИКА:
- Всего шагов: {total_steps}
- Успешно выполнено: {successful_steps}
- Провалилось: {failed_steps}

ЗАДАЧА:
Проанализируй результаты и определи статус:

1. **"success"** - ВСЁ ОТЛИЧНО, можно формировать финальный ответ:
   - Все необходимые шаги выполнены успешно
   - Есть все данные для ответа на вопрос пользователя
   - Нет критических ошибок
   - Нет противоречий

2. **"needs_replan"** - НУЖЕН НОВЫЙ ПЛАН:
   - Некоторые шаги провалились и это критично
   - Нужны альтернативные действия (например, нет прямых рейсов → искать с пересадкой)
   - Обнаружены логические противоречия
   - Данных недостаточно но можно получить другими способами

3. **"needs_user_input"** - НУЖНА ИНФОРМАЦИЯ ОТ ПОЛЬЗОВАТЕЛЯ:
   - Не хватает критической информации которую мы не можем получить сами
   - Нужны уточнения предпочтений
   - Нужны дополнительные параметры

ПРАВИЛА ПРИНЯТИЯ РЕШЕНИЯ:

✓ SUCCESS если:
- Есть данные о погоде ИЛИ рейсах (хотя бы что-то полезное)
- Все шаги с action != "ask_user" выполнены успешно
- Можно дать полезный ответ пользователю

✓ NEEDS_USER_INPUT если:
- Есть шаг с action="ask_user" в результатах
- Недостаточно информации для поиска (нет города вылета, дат, etc.)
- Пользователь должен сделать выбор

✓ NEEDS_REPLAN если:
- Критические ошибки при выполнении НО можно попробовать по-другому
- Результаты противоречивы
- Можно улучшить план

ВАЖНО:
- Не требуй replan если ошибки некритичные
- Если хотя бы ОДИН инструмент сработал успешно → скорее всего SUCCESS
- Будь практичным: лучше дать частичный ответ чем требовать replan

ВЕРНИ ТОЛЬКО JSON (без markdown):
{{
  "status": "success" | "needs_replan" | "needs_user_input",
  "assessment": "детальная оценка результатов (2-3 предложения)",
  "suggestions": ["что можно улучшить или что нужно спросить"],
  "confidence": 0.0-1.0,
  "new_plan": null
}}

Если status="needs_replan", можешь добавить new_plan в формате Plan, но это опционально.
Если status="needs_user_input", в suggestions укажи конкретные вопросы для пользователя.
"""


# ============================================================================
# RESULT REFLECTOR
# ============================================================================

class ResultReflector:
    """
    Рефлектор результатов выполнения планов.

    Анализирует результаты и определяет:
    - Достигнута ли цель
    - Нужен ли replan
    - Нужна ли информация от пользователя
    """

    def __init__(
        self,
        llm: ChatOpenAI,
        max_replans: int = 2
    ):
        """
        Initialize reflector.

        Args:
            llm: Language model for reflection
            max_replans: Maximum number of replans allowed (prevent infinite loops)
        """
        self.llm = llm
        self.max_replans = max_replans

        self.prompt = ChatPromptTemplate.from_template(REFLECTION_PROMPT)

        logger.info(f"ResultReflector initialized (max_replans={max_replans})")

    def _format_plan_steps(self, plan: Plan) -> str:
        """Форматирует шаги плана для промпта."""
        lines = []
        for step in plan.steps:
            lines.append(
                f"{step.id}. {step.description} "
                f"(action={step.action}, params={step.params})"
            )
        return "\n".join(lines)

    def _format_execution_results(self, execution: ExecutionResult) -> str:
        """Форматирует результаты выполнения для промпта."""
        lines = []
        for step_id, result in execution.results.items():
            status = "✓ SUCCESS" if result.success else "✗ FAILED"
            lines.append(f"Step {step_id}: {status}")
            lines.append(f"  Time: {result.execution_time:.2f}s")
            if result.retry_count > 0:
                lines.append(f"  Retries: {result.retry_count}")
            if result.error:
                lines.append(f"  Error: {result.error}")
            if result.data:
                # Ограничиваем размер данных
                data_str = json.dumps(result.data, ensure_ascii=False)[:200]
                lines.append(f"  Data: {data_str}...")

        return "\n".join(lines)

    def _format_errors(self, errors: list) -> str:
        """Форматирует ошибки для промпта."""
        if not errors:
            return "Нет ошибок"

        lines = []
        for i, error in enumerate(errors, 1):
            lines.append(f"{i}. Step {error.get('step_id', 'N/A')}: {error.get('error', 'Unknown error')}")

        return "\n".join(lines)

    async def reflect(
        self,
        original_query: str,
        plan: Plan,
        execution: ExecutionResult,
        replan_count: int = 0
    ) -> ReflectionResult:
        """
        Проанализировать результаты выполнения плана.

        Args:
            original_query: Исходный запрос пользователя
            plan: Выполненный план
            execution: Результаты выполнения
            replan_count: Количество уже выполненных replan (для предотвращения циклов)

        Returns:
            ReflectionResult с оценкой и рекомендациями
        """
        logger.info(f"Reflecting on plan execution (replan_count={replan_count})")

        # Защита от бесконечных replan
        if replan_count >= self.max_replans:
            logger.warning(f"Max replans ({self.max_replans}) reached, forcing success")

            # Проверяем есть ли хоть какие-то успешные результаты
            successful_steps = sum(1 for r in execution.results.values() if r.success)

            if successful_steps > 0:
                return ReflectionResult(
                    status=ReflectionStatus.SUCCESS,
                    assessment=f"Достигнут лимит replans ({self.max_replans}). "
                               f"Используем имеющиеся результаты ({successful_steps} успешных шагов).",
                    suggestions=["Можно улучшить качество, но используем текущие данные"],
                    confidence=0.6
                )
            else:
                return ReflectionResult(
                    status=ReflectionStatus.NEEDS_USER_INPUT,
                    assessment=f"Достигнут лимит replans и нет успешных результатов. "
                               f"Требуется помощь пользователя.",
                    suggestions=["Уточните ваш запрос, пожалуйста"],
                    confidence=0.8
                )

        # Считаем статистику
        total_steps = len(plan.steps)
        successful_steps = sum(1 for r in execution.results.values() if r.success)
        failed_steps = total_steps - successful_steps

        # Форматируем данные для промпта
        plan_steps_str = self._format_plan_steps(plan)
        results_str = self._format_execution_results(execution)
        errors_str = self._format_errors(execution.errors)

        try:
            # Форматируем prompt
            messages = self.prompt.format_messages(
                original_query=original_query,
                plan_goal=plan.goal,
                plan_steps=plan_steps_str,
                execution_results=results_str,
                errors=errors_str,
                total_steps=total_steps,
                successful_steps=successful_steps,
                failed_steps=failed_steps
            )

            # Вызываем LLM
            response = await self.llm.ainvoke(messages)
            response_text = response.content.strip()

            # Парсим JSON
            # Удаляем markdown если есть
            if response_text.startswith("```"):
                lines = response_text.split("\n")
                response_text = "\n".join(
                    line for line in lines
                    if not line.strip().startswith("```")
                )

            result_dict = json.loads(response_text)

            # Создаём ReflectionResult
            reflection = ReflectionResult(
                status=ReflectionStatus(result_dict["status"]),
                assessment=result_dict["assessment"],
                suggestions=result_dict.get("suggestions", []),
                confidence=float(result_dict.get("confidence", 0.8)),
                new_plan=None  # TODO: можно парсить new_plan если нужно
            )

            logger.info(
                f"Reflection complete: status={reflection.status}, "
                f"confidence={reflection.confidence:.2f}"
            )
            logger.info(f"Assessment: {reflection.assessment}")

            return reflection

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM reflection: {response_text[:200]}")
            logger.error(f"JSON error: {e}")

            # Fallback - базовый анализ
            return self._fallback_reflection(execution, successful_steps, total_steps)

        except Exception as e:
            logger.error(f"Error in reflection: {e}", exc_info=True)
            return self._fallback_reflection(execution, successful_steps, total_steps)

    def _fallback_reflection(
        self,
        execution: ExecutionResult,
        successful_steps: int,
        total_steps: int
    ) -> ReflectionResult:
        """
        Fallback рефлексия на основе простых правил (когда LLM не работает).

        Args:
            execution: Результаты выполнения
            successful_steps: Количество успешных шагов
            total_steps: Всего шагов

        Returns:
            ReflectionResult
        """
        logger.info("Using fallback reflection logic")

        # Проверяем есть ли ask_user в результатах
        has_ask_user = any(
            r.success and isinstance(r.data, dict) and r.data.get("action") == "ask_user"
            for r in execution.results.values()
        )

        if has_ask_user:
            # Нужен ввод пользователя
            questions = []
            for r in execution.results.values():
                if isinstance(r.data, dict) and r.data.get("action") == "ask_user":
                    questions.extend(r.data.get("questions", []))

            return ReflectionResult(
                status=ReflectionStatus.NEEDS_USER_INPUT,
                assessment="Обнаружен шаг ask_user - требуется информация от пользователя",
                suggestions=questions if questions else ["Уточните ваш запрос"],
                confidence=0.9
            )

        # Проверяем успешность
        success_rate = successful_steps / total_steps if total_steps > 0 else 0

        if success_rate >= 0.5:
            # Хотя бы половина успешна
            return ReflectionResult(
                status=ReflectionStatus.SUCCESS,
                assessment=f"Выполнено {successful_steps} из {total_steps} шагов успешно. Можно формировать ответ.",
                suggestions=[],
                confidence=0.7
            )
        elif successful_steps > 0:
            # Есть успешные шаги но меньше половины
            return ReflectionResult(
                status=ReflectionStatus.SUCCESS,
                assessment=f"Частичный успех: {successful_steps}/{total_steps} шагов. Используем доступные данные.",
                suggestions=["Некоторые данные недоступны, ответ может быть неполным"],
                confidence=0.5
            )
        else:
            # Все провалилось
            return ReflectionResult(
                status=ReflectionStatus.NEEDS_USER_INPUT,
                assessment="Все шаги провалились. Требуется уточнение запроса.",
                suggestions=["Уточните ваш запрос или попробуйте переформулировать"],
                confidence=0.8
            )


# ============================================================================
# TESTS
# ============================================================================

if __name__ == "__main__":
    """Тестирование reflector."""
    import asyncio
    import os
    from dotenv import load_dotenv
    from models import Plan, Step, ExecutionResult, StepResult

    load_dotenv()

    async def test_reflector():
        """Test result reflector"""
        print("Testing Result Reflector...\n")

        # Инициализируем LLM
        llm = ChatOpenAI(
            model="gpt-4o-mini",
            temperature=0.0,
            api_key=os.getenv("OPENAI_API_KEY")
        )

        reflector = ResultReflector(llm)

        # Test case 1: Successful execution
        print("="*60)
        print("Test 1: Successful execution")
        print("="*60)

        plan1 = Plan(
            goal="Find flights and weather",
            steps=[
                Step(id=1, action="get_weather", params={"city": "Paris"}, description="Get weather"),
                Step(id=2, action="search_flights", params={}, description="Search flights")
            ],
            total_estimated_time=10
        )

        execution1 = ExecutionResult(
            success=True,
            results={
                1: StepResult(step_id=1, success=True, data={"temp": "20C"}, execution_time=1.0),
                2: StepResult(step_id=2, success=True, data={"flights": ["FL001"]}, execution_time=2.0)
            },
            errors=[],
            total_execution_time=3.0
        )

        result1 = await reflector.reflect(
            "Найди рейсы в Париж",
            plan1,
            execution1
        )

        print(f"Status: {result1.status}")
        print(f"Assessment: {result1.assessment}")
        print(f"Suggestions: {result1.suggestions}")
        print(f"Confidence: {result1.confidence}\n")

        # Test case 2: Needs user input
        print("="*60)
        print("Test 2: Needs user input")
        print("="*60)

        plan2 = Plan(
            goal="Plan trip",
            steps=[
                Step(id=1, action="ask_user", params={}, description="Ask user")
            ],
            total_estimated_time=0
        )

        execution2 = ExecutionResult(
            success=True,
            results={
                1: StepResult(
                    step_id=1,
                    success=True,
                    data={"action": "ask_user", "questions": ["From which city?"]},
                    execution_time=0.0
                )
            },
            errors=[],
            total_execution_time=0.0
        )

        result2 = await reflector.reflect(
            "Спланируй поездку",
            plan2,
            execution2
        )

        print(f"Status: {result2.status}")
        print(f"Assessment: {result2.assessment}")
        print(f"Suggestions: {result2.suggestions}")
        print(f"Confidence: {result2.confidence}\n")

    # Run tests
    asyncio.run(test_reflector())
