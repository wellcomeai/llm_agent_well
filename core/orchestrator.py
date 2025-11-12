"""
Plan Orchestrator для параллельного выполнения планов.

Выполняет план с учетом зависимостей (DAG traversal):
- Параллельно выполняет независимые шаги
- Управляет зависимостями между шагами
- Retry логика для временных ошибок
- Real-time streaming событий
"""

import logging
import asyncio
import time
import json
from typing import Dict, Any, Callable, Optional, List
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
import networkx as nx

try:
    from .models import Plan, Step, StepResult, ExecutionResult
except ImportError:
    # Для прямого запуска файла
    from models import Plan, Step, StepResult, ExecutionResult

logger = logging.getLogger(__name__)


# ============================================================================
# RETRY CONFIGURATION
# ============================================================================

RETRY_CONFIG = {
    "max_retries": 3,
    "backoff_factor": 2,  # Exponential backoff: 1s, 2s, 4s
    "retry_on": [
        TimeoutError,
        ConnectionError,
        # asyncio.TimeoutError,  # Добавлено для async
    ],
    "skip_on": [
        ValueError,
        KeyError,
        TypeError,
    ]
}


# ============================================================================
# PLAN ORCHESTRATOR
# ============================================================================

class PlanOrchestrator:
    """
    Оркестратор выполнения планов с параллелизацией.

    Функции:
    - Параллельное выполнение независимых шагов
    - Управление зависимостями (DAG)
    - Retry логика
    - Streaming событий
    """

    def __init__(
        self,
        tools: Dict[str, Callable],
        max_workers: int = 5,
        step_timeout: int = 30
    ):
        """
        Initialize orchestrator.

        Args:
            tools: Словарь доступных инструментов {name: callable}
            max_workers: Максимальное количество параллельных workers
            step_timeout: Таймаут для выполнения одного шага (секунды)
        """
        self.tools = tools
        self.max_workers = max_workers
        self.step_timeout = step_timeout

        # Thread pool для параллельного выполнения
        self.executor = ThreadPoolExecutor(max_workers=max_workers)

        logger.info(
            f"PlanOrchestrator initialized "
            f"(max_workers={max_workers}, step_timeout={step_timeout}s)"
        )

    def _build_dependency_graph(self, plan: Plan) -> nx.DiGraph:
        """
        Построить граф зависимостей из плана.

        Args:
            plan: План для выполнения

        Returns:
            NetworkX directed graph
        """
        G = nx.DiGraph()

        # Добавляем узлы (шаги)
        for step in plan.steps:
            G.add_node(step.id, step=step)

        # Добавляем рёбра (зависимости)
        for step in plan.steps:
            for dep_id in step.depends_on:
                # Ребро от dep_id к step.id (dep_id должен выполниться раньше)
                G.add_edge(dep_id, step.id)

        logger.info(
            f"Dependency graph built: {len(G.nodes)} nodes, {len(G.edges)} edges"
        )

        return G

    def _get_execution_levels(self, graph: nx.DiGraph) -> List[List[int]]:
        """
        Группировка шагов по уровням для параллельного выполнения.

        Использует топологическую сортировку:
        - Level 0: шаги без зависимостей
        - Level 1: шаги зависящие только от Level 0
        - И т.д.

        Args:
            graph: Граф зависимостей

        Returns:
            Список уровней, каждый уровень = список step IDs
        """
        levels = []
        remaining_nodes = set(graph.nodes())

        while remaining_nodes:
            # Находим узлы без невыполненных зависимостей
            current_level = []

            for node in remaining_nodes:
                # Получаем предков (зависимости)
                predecessors = set(graph.predecessors(node))

                # Если все предки уже выполнены (не в remaining_nodes)
                if predecessors.isdisjoint(remaining_nodes):
                    current_level.append(node)

            if not current_level:
                # Не должно произойти если граф ациклический
                raise ValueError("Circular dependency detected in execution graph!")

            levels.append(sorted(current_level))
            remaining_nodes -= set(current_level)

        logger.info(f"Execution levels: {len(levels)} levels")
        for i, level in enumerate(levels):
            logger.debug(f"  Level {i}: steps {level}")

        return levels

    async def _execute_step_with_retry(
        self,
        step: Step,
        step_results: Dict[int, StepResult]
    ) -> StepResult:
        """
        Выполнить один шаг с retry логикой.

        Args:
            step: Шаг для выполнения
            step_results: Результаты предыдущих шагов (для зависимостей)

        Returns:
            StepResult с результатом выполнения
        """
        retry_count = 0
        last_error = None

        for attempt in range(RETRY_CONFIG["max_retries"] + 1):
            try:
                start_time = time.time()

                # Выполняем шаг
                result_data = await self._execute_single_step(step, step_results)

                execution_time = time.time() - start_time

                # Успех!
                return StepResult(
                    step_id=step.id,
                    success=True,
                    data=result_data,
                    error=None,
                    execution_time=execution_time,
                    retry_count=retry_count
                )

            except Exception as e:
                last_error = e
                error_type = type(e)

                # Проверяем можно ли retry
                if error_type in RETRY_CONFIG["skip_on"]:
                    # Логические ошибки - не retry
                    logger.error(f"Step {step.id} failed with non-retryable error: {e}")
                    break

                if error_type in RETRY_CONFIG["retry_on"] and attempt < RETRY_CONFIG["max_retries"]:
                    # Retry для временных ошибок
                    retry_count += 1
                    backoff = RETRY_CONFIG["backoff_factor"] ** attempt

                    logger.warning(
                        f"Step {step.id} failed (attempt {attempt + 1}), "
                        f"retrying in {backoff}s: {e}"
                    )

                    await asyncio.sleep(backoff)
                    continue
                else:
                    # Исчерпаны retry или неизвестная ошибка
                    logger.error(f"Step {step.id} failed after {retry_count} retries: {e}")
                    break

        # Если дошли сюда - шаг провалился
        execution_time = time.time() - start_time

        return StepResult(
            step_id=step.id,
            success=False,
            data=None,
            error=str(last_error),
            execution_time=execution_time,
            retry_count=retry_count
        )

    async def _execute_single_step(
        self,
        step: Step,
        step_results: Dict[int, StepResult]
    ) -> Any:
        """
        Выполнить один шаг (без retry).

        Args:
            step: Шаг для выполнения
            step_results: Результаты предыдущих шагов

        Returns:
            Данные результата выполнения

        Raises:
            Exception: Любые ошибки при выполнении
        """
        logger.info(f"Executing step {step.id}: {step.action}")

        # Специальная обработка виртуальных действий
        if step.action == "ask_user":
            # Возвращаем вопросы для пользователя
            return {
                "action": "ask_user",
                "questions": step.params.get("questions", [])
            }

        if step.action == "synthesize_response":
            # Собираем данные из предыдущих шагов
            data_from = step.params.get("data_from", [])
            collected_data = {}

            for step_id in data_from:
                if step_id in step_results:
                    collected_data[f"step_{step_id}"] = step_results[step_id].data

            return {
                "action": "synthesize",
                "collected_data": collected_data
            }

        # Реальные инструменты
        if step.action not in self.tools:
            raise ValueError(f"Tool '{step.action}' not found in available tools")

        tool = self.tools[step.action]

        # Выполняем инструмент
        # Предполагаем что инструменты могут быть sync или async
        if asyncio.iscoroutinefunction(tool):
            result = await asyncio.wait_for(
                tool(**step.params),
                timeout=self.step_timeout
            )
        else:
            # Sync функции выполняем в executor
            loop = asyncio.get_event_loop()
            result = await asyncio.wait_for(
                loop.run_in_executor(self.executor, lambda: tool(**step.params)),
                timeout=self.step_timeout
            )

        logger.info(f"Step {step.id} completed successfully")
        return result

    async def execute_plan(
        self,
        plan: Plan,
        stream_callback: Optional[Callable] = None
    ) -> ExecutionResult:
        """
        Выполнить план с параллелизацией.

        Алгоритм:
        1. Строим граф зависимостей (DAG)
        2. Топологическая сортировка → уровни выполнения
        3. Каждый уровень выполняем параллельно
        4. Собираем результаты
        5. Обрабатываем ошибки

        Args:
            plan: План для выполнения
            stream_callback: Опциональный callback для streaming событий

        Returns:
            ExecutionResult с результатами всех шагов
        """
        logger.info(f"=== Starting plan execution: {len(plan.steps)} steps ===")

        start_time = time.time()
        step_results: Dict[int, StepResult] = {}
        errors: List[Dict[str, Any]] = []

        # Stream событие: plan started
        if stream_callback:
            await stream_callback({
                "event_type": "plan_started",
                "data": {
                    "goal": plan.goal,
                    "total_steps": len(plan.steps),
                    "estimated_time": plan.total_estimated_time
                },
                "timestamp": datetime.now().isoformat()
            })

        try:
            # 1. Строим граф зависимостей
            graph = self._build_dependency_graph(plan)

            # 2. Получаем уровни выполнения
            execution_levels = self._get_execution_levels(graph)

            # 3. Выполняем по уровням
            for level_num, level_step_ids in enumerate(execution_levels):
                logger.info(f"Executing level {level_num}: steps {level_step_ids}")

                # Stream событие: level started
                if stream_callback:
                    await stream_callback({
                        "event_type": "level_started",
                        "data": {
                            "level": level_num,
                            "step_ids": level_step_ids
                        },
                        "timestamp": datetime.now().isoformat()
                    })

                # Получаем Step объекты для текущего уровня
                level_steps = [
                    graph.nodes[step_id]["step"]
                    for step_id in level_step_ids
                ]

                # Выполняем шаги параллельно
                level_tasks = [
                    self._execute_step_with_retry(step, step_results)
                    for step in level_steps
                ]

                # Stream событие: steps started
                if stream_callback:
                    for step in level_steps:
                        await stream_callback({
                            "event_type": "step_started",
                            "step_id": step.id,
                            "data": {
                                "action": step.action,
                                "description": step.description,
                                "params": step.params
                            },
                            "timestamp": datetime.now().isoformat()
                        })

                # Ждём завершения всех шагов уровня
                level_results = await asyncio.gather(*level_tasks)

                # Сохраняем результаты
                for result in level_results:
                    step_results[result.step_id] = result

                    # Stream событие: step completed/failed
                    if stream_callback:
                        await stream_callback({
                            "event_type": "step_completed" if result.success else "step_failed",
                            "step_id": result.step_id,
                            "data": {
                                "success": result.success,
                                "execution_time": result.execution_time,
                                "retry_count": result.retry_count,
                                "error": result.error,
                                "data": result.data
                            },
                            "timestamp": datetime.now().isoformat()
                        })

                    # Собираем ошибки
                    if not result.success:
                        errors.append({
                            "step_id": result.step_id,
                            "error": result.error,
                            "retry_count": result.retry_count
                        })

                logger.info(f"Level {level_num} completed")

        except Exception as e:
            logger.error(f"Critical error during plan execution: {e}", exc_info=True)

            errors.append({
                "step_id": None,
                "error": f"Critical execution error: {str(e)}",
                "type": "critical"
            })

        # Вычисляем итоговое время
        total_time = time.time() - start_time

        # Определяем успешность
        success = len(errors) == 0

        logger.info(
            f"=== Plan execution completed: "
            f"success={success}, time={total_time:.2f}s, errors={len(errors)} ==="
        )

        # Stream событие: plan completed
        if stream_callback:
            await stream_callback({
                "event_type": "plan_completed",
                "data": {
                    "success": success,
                    "total_time": total_time,
                    "steps_completed": len(step_results),
                    "errors_count": len(errors)
                },
                "timestamp": datetime.now().isoformat()
            })

        return ExecutionResult(
            success=success,
            results=step_results,
            errors=errors,
            total_execution_time=total_time
        )

    def shutdown(self):
        """Закрыть executor."""
        logger.info("Shutting down orchestrator")
        self.executor.shutdown(wait=True)


# ============================================================================
# TESTS
# ============================================================================

if __name__ == "__main__":
    """Тестирование orchestrator."""
    import asyncio

    async def test_orchestrator():
        """Test plan orchestrator"""
        print("Testing Plan Orchestrator...\n")

        # Mock tools
        async def mock_weather(city: str):
            """Mock weather API"""
            await asyncio.sleep(1)  # Simulate API call
            return {"city": city, "temp": "20C", "condition": "Sunny"}

        async def mock_flights(from_city: str, to_city: str, date: str):
            """Mock flights API"""
            await asyncio.sleep(2)  # Simulate API call
            return {
                "from": from_city,
                "to": to_city,
                "date": date,
                "flights": ["FL001", "FL002"]
            }

        tools = {
            "get_weather": mock_weather,
            "search_flights": mock_flights
        }

        orchestrator = PlanOrchestrator(tools, max_workers=3)

        # Создаём тестовый план
        from models import Plan, Step

        plan = Plan(
            goal="Test parallel execution",
            steps=[
                Step(
                    id=1,
                    action="get_weather",
                    params={"city": "Paris"},
                    depends_on=[],
                    can_parallel=True,
                    description="Get weather in Paris",
                    estimated_time_sec=3
                ),
                Step(
                    id=2,
                    action="search_flights",
                    params={
                        "from_city": "Moscow",
                        "to_city": "Paris",
                        "date": "2025-01-20"
                    },
                    depends_on=[],
                    can_parallel=True,
                    description="Search flights",
                    estimated_time_sec=5
                ),
                Step(
                    id=3,
                    action="synthesize_response",
                    params={"data_from": [1, 2]},
                    depends_on=[1, 2],
                    can_parallel=False,
                    description="Synthesize response",
                    estimated_time_sec=2
                )
            ],
            total_estimated_time=7
        )

        # Stream callback
        async def stream_cb(event):
            print(f"[{event['event_type']}] {event.get('data', {})}")

        # Выполняем план
        print("Executing plan...")
        start = time.time()

        result = await orchestrator.execute_plan(plan, stream_callback=stream_cb)

        duration = time.time() - start

        print(f"\n{'='*60}")
        print(f"Execution completed:")
        print(f"  Success: {result.success}")
        print(f"  Total time: {duration:.2f}s (estimated: {plan.total_estimated_time}s)")
        print(f"  Steps completed: {len(result.results)}")
        print(f"  Errors: {len(result.errors)}")

        if duration < 3.5:  # Параллельное выполнение должно быть быстрее
            print(f"  ✓ Parallel execution works! (faster than sequential)")
        else:
            print(f"  ✗ Sequential execution (should be parallel)")

        print("\nStep results:")
        for step_id, step_result in result.results.items():
            print(f"  Step {step_id}: success={step_result.success}, time={step_result.execution_time:.2f}s")

        orchestrator.shutdown()

    # Run tests
    asyncio.run(test_orchestrator())
