"""
Core components for Plan-and-Execute architecture.

Компоненты:
- models: Pydantic модели данных
- router: Классификация запросов (simple vs agent) + IntentClassifier
- planner: Создание планов выполнения
- orchestrator: Параллельное выполнение планов
- reflector: Рефлексия и проверка результатов
- state_manager: Управление состоянием сессий (TravelContext, StateManager)
- context_extractor: Извлечение сущностей из истории диалога
"""

__version__ = "2.1.0"
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

from .state_manager import TravelContext, StateManager
from .context_extractor import ContextExtractor
from .router import IntentClassifier

__all__ = [
    # Models
    "RouteType",
    "RouteDecision",
    "Step",
    "Plan",
    "StepResult",
    "ExecutionResult",
    "ReflectionStatus",
    "ReflectionResult",
    # State Management
    "TravelContext",
    "StateManager",
    "ContextExtractor",
    "IntentClassifier",
]
