"""
Pydantic модели для Plan-and-Execute архитектуры.

Определяет все структуры данных используемые в системе:
- RouteDecision: Решение о маршрутизации запроса
- Plan: Структурированный план выполнения
- Step: Отдельный шаг плана
- ExecutionResult: Результат выполнения плана
- ReflectionResult: Результат рефлексии
"""

from pydantic import BaseModel, Field, field_validator
from typing import List, Dict, Any, Optional, Literal
from datetime import datetime
from enum import Enum
import logging

logger = logging.getLogger(__name__)


# ============================================================================
# ENUMS
# ============================================================================

class RouteType(str, Enum):
    """Тип маршрутизации запроса."""
    SIMPLE = "simple"      # Простой вопрос - прямой ответ LLM
    AGENT = "agent"        # Требуется агент с инструментами


class ReflectionStatus(str, Enum):
    """Статус рефлексии результатов."""
    SUCCESS = "success"                 # Всё отлично
    NEEDS_REPLAN = "needs_replan"       # Нужен новый план
    NEEDS_USER_INPUT = "needs_user_input"  # Нужна информация от пользователя


# ============================================================================
# ROUTING
# ============================================================================

class RouteDecision(BaseModel):
    """
    Решение о маршрутизации запроса.

    Определяет нужен ли агент с инструментами или можно ответить напрямую.
    """
    route_type: RouteType
    confidence: float = Field(ge=0.0, le=1.0, description="Уверенность в решении (0-1)")
    reasoning: str = Field(description="Объяснение почему такое решение")
    direct_answer: Optional[str] = Field(default=None, description="Прямой ответ если route_type=SIMPLE")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "route_type": "simple",
                    "confidence": 0.95,
                    "reasoning": "Простой вопрос о столице - не требует инструментов",
                    "direct_answer": "Столица Франции - Париж"
                }
            ]
        }
    }


# ============================================================================
# PLANNING
# ============================================================================

class Step(BaseModel):
    """
    Отдельный шаг в плане выполнения.

    Представляет атомарное действие: вызов функции, запрос к пользователю, или синтез ответа.
    """
    id: int = Field(description="Уникальный ID шага")
    action: str = Field(description="Имя функции или действия (например: get_weather, search_flights, ask_user)")
    params: Dict[str, Any] = Field(default_factory=dict, description="Параметры для функции")
    depends_on: List[int] = Field(default_factory=list, description="ID шагов от которых зависит этот шаг")
    can_parallel: bool = Field(default=True, description="Можно ли выполнять параллельно с другими шагами")
    description: str = Field(description="Человеко-читаемое описание что делает шаг")
    estimated_time_sec: int = Field(default=5, description="Оценка времени выполнения в секундах")

    @field_validator('depends_on')
    @classmethod
    def no_self_dependency(cls, v: List[int], info) -> List[int]:
        """Проверка что шаг не зависит сам от себя."""
        if 'id' in info.data and info.data['id'] in v:
            raise ValueError(f"Step {info.data['id']} cannot depend on itself")
        return v

    @field_validator('id')
    @classmethod
    def id_must_be_positive(cls, v: int) -> int:
        """ID должен быть положительным."""
        if v <= 0:
            raise ValueError(f"Step ID must be positive, got {v}")
        return v

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "id": 1,
                    "action": "get_weather",
                    "params": {"city": "Paris"},
                    "depends_on": [],
                    "can_parallel": True,
                    "description": "Проверить погоду в Париже",
                    "estimated_time_sec": 3
                }
            ]
        }
    }


class Plan(BaseModel):
    """
    Полный план выполнения задачи.

    Содержит последовательность шагов с зависимостями (DAG).
    """
    goal: str = Field(description="Цель/задача которую решает план")
    steps: List[Step] = Field(description="Список шагов для выполнения")
    total_estimated_time: int = Field(description="Общее оценочное время выполнения в секундах")
    created_at: datetime = Field(default_factory=datetime.now, description="Время создания плана")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Дополнительная метаинформация")

    @field_validator('steps')
    @classmethod
    def validate_step_dependencies(cls, v: List[Step]) -> List[Step]:
        """
        Проверяет что все зависимости указывают на существующие шаги.
        """
        if not v:
            return v

        step_ids = {step.id for step in v}

        for step in v:
            for dep_id in step.depends_on:
                if dep_id not in step_ids:
                    raise ValueError(
                        f"Step {step.id} depends on non-existent step {dep_id}. "
                        f"Available step IDs: {sorted(step_ids)}"
                    )

        return v

    @field_validator('steps')
    @classmethod
    def validate_no_circular_dependencies(cls, v: List[Step]) -> List[Step]:
        """
        Проверяет отсутствие циклических зависимостей в плане (DAG validation).

        Использует DFS для обнаружения циклов.
        """
        if not v:
            return v

        # Строим граф зависимостей
        graph = {step.id: step.depends_on for step in v}

        # DFS для поиска циклов
        visited = set()
        rec_stack = set()

        def has_cycle(node_id: int) -> bool:
            """Рекурсивная проверка на цикл через DFS."""
            visited.add(node_id)
            rec_stack.add(node_id)

            # Проверяем все зависимости
            for dep_id in graph.get(node_id, []):
                if dep_id not in visited:
                    if has_cycle(dep_id):
                        return True
                elif dep_id in rec_stack:
                    # Нашли цикл!
                    return True

            rec_stack.remove(node_id)
            return False

        # Проверяем каждый узел
        for step in v:
            if step.id not in visited:
                if has_cycle(step.id):
                    raise ValueError(
                        f"Circular dependency detected in plan! "
                        f"Step {step.id} creates a cycle in the dependency graph."
                    )

        logger.info(f"Plan validated: {len(v)} steps, no circular dependencies")
        return v

    @field_validator('steps')
    @classmethod
    def validate_unique_step_ids(cls, v: List[Step]) -> List[Step]:
        """Проверяет что все ID шагов уникальны."""
        if not v:
            return v

        step_ids = [step.id for step in v]
        if len(step_ids) != len(set(step_ids)):
            duplicates = [id for id in step_ids if step_ids.count(id) > 1]
            raise ValueError(f"Duplicate step IDs found: {set(duplicates)}")

        return v

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "goal": "Найти рейсы Москва→Париж на 20 января",
                    "steps": [
                        {
                            "id": 1,
                            "action": "get_weather",
                            "params": {"city": "Paris"},
                            "depends_on": [],
                            "can_parallel": True,
                            "description": "Проверить погоду в Париже",
                            "estimated_time_sec": 3
                        },
                        {
                            "id": 2,
                            "action": "search_flights",
                            "params": {
                                "from_city": "Moscow",
                                "to_city": "Paris",
                                "date": "2025-01-20"
                            },
                            "depends_on": [],
                            "can_parallel": True,
                            "description": "Найти рейсы Москва→Париж",
                            "estimated_time_sec": 5
                        }
                    ],
                    "total_estimated_time": 5,
                    "created_at": "2025-01-15T10:00:00",
                    "metadata": {"user_query": "Найди рейсы в Париж на 20 января"}
                }
            ]
        }
    }


# ============================================================================
# EXECUTION
# ============================================================================

class StepResult(BaseModel):
    """
    Результат выполнения одного шага.
    """
    step_id: int = Field(description="ID выполненного шага")
    success: bool = Field(description="Успешно ли выполнен шаг")
    data: Any = Field(default=None, description="Данные результата")
    error: Optional[str] = Field(default=None, description="Сообщение об ошибке если была")
    execution_time: float = Field(description="Время выполнения в секундах")
    timestamp: datetime = Field(default_factory=datetime.now, description="Время завершения")
    retry_count: int = Field(default=0, description="Количество повторных попыток")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "step_id": 1,
                    "success": True,
                    "data": {"temperature_c": "12", "description": "Cloudy"},
                    "error": None,
                    "execution_time": 1.2,
                    "timestamp": "2025-01-15T10:00:01",
                    "retry_count": 0
                }
            ]
        }
    }


class ExecutionResult(BaseModel):
    """
    Результат выполнения всего плана.
    """
    success: bool = Field(description="Успешно ли выполнен план")
    results: Dict[int, StepResult] = Field(description="Результаты по каждому шагу (step_id -> result)")
    errors: List[Dict[str, Any]] = Field(default_factory=list, description="Список ошибок если были")
    total_execution_time: float = Field(description="Общее время выполнения в секундах")
    timestamp: datetime = Field(default_factory=datetime.now, description="Время завершения")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "success": True,
                    "results": {
                        1: {
                            "step_id": 1,
                            "success": True,
                            "data": {"temperature_c": "12"},
                            "execution_time": 1.2,
                            "timestamp": "2025-01-15T10:00:01"
                        }
                    },
                    "errors": [],
                    "total_execution_time": 3.5,
                    "timestamp": "2025-01-15T10:00:03"
                }
            ]
        }
    }


# ============================================================================
# REFLECTION
# ============================================================================

class ReflectionResult(BaseModel):
    """
    Результат рефлексии/проверки выполнения плана.

    Определяет нужны ли дополнительные действия или план выполнен успешно.
    """
    status: ReflectionStatus = Field(description="Статус рефлексии")
    assessment: str = Field(description="Детальная оценка результатов")
    suggestions: List[str] = Field(default_factory=list, description="Предложения по улучшению")
    new_plan: Optional[Plan] = Field(default=None, description="Новый план если нужен replan")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Уверенность в оценке")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "status": "success",
                    "assessment": "Все шаги выполнены успешно, получены данные о погоде и рейсах",
                    "suggestions": [],
                    "new_plan": None,
                    "confidence": 0.95
                },
                {
                    "status": "needs_user_input",
                    "assessment": "Не хватает информации о городе вылета",
                    "suggestions": ["Спросить у пользователя город вылета"],
                    "new_plan": None,
                    "confidence": 0.9
                }
            ]
        }
    }


# ============================================================================
# VALIDATION TESTS
# ============================================================================

if __name__ == "__main__":
    """Тестирование валидации моделей."""

    print("Testing Pydantic models...\n")

    # Test 1: Valid plan
    print("1. Testing valid plan:")
    try:
        plan = Plan(
            goal="Test plan",
            steps=[
                Step(id=1, action="get_weather", params={"city": "Paris"}, description="Get weather"),
                Step(id=2, action="search_flights", params={}, depends_on=[1], description="Search flights")
            ],
            total_estimated_time=10
        )
        print(f"✓ Valid plan created with {len(plan.steps)} steps\n")
    except Exception as e:
        print(f"✗ Failed: {e}\n")

    # Test 2: Circular dependency
    print("2. Testing circular dependency detection:")
    try:
        plan = Plan(
            goal="Test circular",
            steps=[
                Step(id=1, action="action1", params={}, depends_on=[2], description="Step 1"),
                Step(id=2, action="action2", params={}, depends_on=[1], description="Step 2")
            ],
            total_estimated_time=10
        )
        print("✗ Should have failed but didn't!\n")
    except ValueError as e:
        print(f"✓ Correctly caught circular dependency: {e}\n")

    # Test 3: Non-existent dependency
    print("3. Testing non-existent dependency:")
    try:
        plan = Plan(
            goal="Test invalid dep",
            steps=[
                Step(id=1, action="action1", params={}, depends_on=[999], description="Step 1")
            ],
            total_estimated_time=10
        )
        print("✗ Should have failed but didn't!\n")
    except ValueError as e:
        print(f"✓ Correctly caught invalid dependency: {e}\n")

    # Test 4: Self dependency
    print("4. Testing self dependency:")
    try:
        step = Step(id=1, action="action1", params={}, depends_on=[1], description="Step 1")
        print("✗ Should have failed but didn't!\n")
    except ValueError as e:
        print(f"✓ Correctly caught self dependency: {e}\n")

    # Test 5: Duplicate step IDs
    print("5. Testing duplicate step IDs:")
    try:
        plan = Plan(
            goal="Test duplicates",
            steps=[
                Step(id=1, action="action1", params={}, description="Step 1"),
                Step(id=1, action="action2", params={}, description="Step 1 again")
            ],
            total_estimated_time=10
        )
        print("✗ Should have failed but didn't!\n")
    except ValueError as e:
        print(f"✓ Correctly caught duplicate IDs: {e}\n")

    # Test 6: RouteDecision
    print("6. Testing RouteDecision:")
    try:
        decision = RouteDecision(
            route_type=RouteType.SIMPLE,
            confidence=0.95,
            reasoning="Simple question",
            direct_answer="Answer"
        )
        print(f"✓ RouteDecision created: {decision.route_type}\n")
    except Exception as e:
        print(f"✗ Failed: {e}\n")

    print("All tests completed!")
