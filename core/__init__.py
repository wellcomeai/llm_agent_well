"""
Core components for Plan-and-Execute architecture.

Компоненты:
- models: Pydantic модели данных
- router: Классификация запросов (simple vs agent)
- planner: Создание планов выполнения
- orchestrator: Параллельное выполнение планов
- reflector: Рефлексия и проверка результатов
"""

__version__ = "2.0.0"
__architecture__ = "plan-and-execute"

from .models import (
    RouteType,
    RouteDecision,
    Step,
    Plan,
    StepResult,
    ExecutionResult,
    ReflectionStatus,
    ReflectionResult,
)

__all__ = [
    "RouteType",
    "RouteDecision",
    "Step",
    "Plan",
    "StepResult",
    "ExecutionResult",
    "ReflectionStatus",
    "ReflectionResult",
]
