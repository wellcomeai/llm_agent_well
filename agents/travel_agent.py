"""
Travel Agent with Plan-and-Execute Architecture - Version 2.1

Новая архитектура с Context Management:
1. Router → классификация запросов (simple vs agent)
2. ContextExtractor → извлечение сущностей из истории диалога
3. StateManager → управление состоянием путешествия (TravelContext)
4. IntentClassifier → определение намерения пользователя
5. Planner → создание структурированных планов с обогащённым контекстом
6. Orchestrator → параллельное выполнение
7. Reflector → проверка результатов и replan

Преимущества над ReAct:
- Параллельное выполнение независимых шагов
- Показ плана пользователю ДО выполнения
- Меньше путаницы в контексте
- Лучше handling ошибок
- Автоматическое извлечение контекста из истории диалога
- Интеллектуальная обработка коротких уточнений
- Проверка полноты данных перед выполнением действий
"""

import os
import logging
import json
from datetime import datetime
from typing import AsyncGenerator, Dict, Any, Optional
from langchain_openai import ChatOpenAI
from langchain.memory import ConversationSummaryBufferMemory
from dotenv import load_dotenv

# Import core components
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.router import QueryRouter, IntentClassifier
from core.planner import TaskPlanner
from core.orchestrator import PlanOrchestrator
from core.reflector import ResultReflector
from core.models import RouteType, ReflectionStatus
from core.state_manager import StateManager, TravelContext
from core.context_extractor import ContextExtractor

# Import tools
from functions.weather import get_weather
from functions.flights import search_flights

load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============================================================================
# TRAVEL AGENT V2 (Plan-and-Execute)
# ============================================================================

class TravelAgent:
    """
    Travel Agent с Plan-and-Execute архитектурой и Context Management.

    Pipeline:
    1. Router → определить нужен ли агент
    2. ContextExtractor → извлечь сущности из истории
    3. IntentClassifier → определить намерение пользователя
    4. Check completeness → проверить достаточно ли данных
    5. Planner → создать план с контекстом
    6. Показать план пользователю
    7. Orchestrator → выполнить параллельно
    8. Reflector → проверить результаты
    9. Если нужен replan → goto 5
    10. Синтезировать финальный ответ

    Components:
    - StateManager: Управление состоянием сессий (города, даты, пассажиры)
    - ContextExtractor: Извлечение сущностей из истории диалога
    - IntentClassifier: Классификация намерений (weather_check, flight_search, etc.)
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: str = "gpt-4o-mini",
        temperature: float = 0.7,
        max_tokens: int = 2000
    ):
        """Initialize Travel Agent V2."""
        logger.info("=== Initializing TravelAgent V2 (Plan-and-Execute) ===")

        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY не найден в environment variables")

        self.model_name = model_name
        self.temperature = temperature
        self.max_tokens = max_tokens

        # Initialize LLM
        self.llm = ChatOpenAI(
            model=model_name,
            temperature=temperature,
            max_tokens=max_tokens,
            streaming=True,
            api_key=self.api_key
        )
        logger.info(f"LLM initialized: {model_name}")

        # Prepare tools
        self.tools_dict = {
            "get_weather": get_weather,
            "search_flights": search_flights
        }

        # Initialize components
        self.router = QueryRouter(self.llm)
        self.planner = TaskPlanner(self.llm)
        self.orchestrator = PlanOrchestrator(self.tools_dict, max_workers=5)
        self.reflector = ResultReflector(self.llm, max_replans=2)

        # New: Context management components
        self.state_manager = StateManager()
        self.context_extractor = ContextExtractor(self.llm)
        self.intent_classifier = IntentClassifier()

        logger.info("All components initialized successfully")

        # Session memories
        self.memories: Dict[str, ConversationSummaryBufferMemory] = {}

        logger.info("TravelAgent V2 ready with context management!")

    def _get_memory(self, session_id: str) -> ConversationSummaryBufferMemory:
        """Get or create memory for session."""
        if session_id not in self.memories:
            logger.info(f"Creating new memory for session: {session_id}")

            self.memories[session_id] = ConversationSummaryBufferMemory(
                llm=self.llm,
                max_token_limit=1000,
                memory_key="chat_history",
                return_messages=True
            )

        return self.memories[session_id]

    async def _extract_and_update_context(
        self,
        query: str,
        session_id: str,
        memory: ConversationSummaryBufferMemory
    ) -> TravelContext:
        """
        Извлечь контекст из истории и обновить состояние.

        Args:
            query: Текущий запрос
            session_id: ID сессии
            memory: Память сессии

        Returns:
            TravelContext: Обновлённое состояние
        """
        logger.info("Extracting context from conversation history")

        # Получить историю из памяти
        chat_history = []
        if hasattr(memory, 'chat_memory') and memory.chat_memory.messages:
            for msg in memory.chat_memory.messages:
                chat_history.append({
                    "role": msg.type,
                    "content": msg.content
                })

        # Извлечь сущности (города, даты, пассажиры)
        extracted = self.context_extractor.extract_context(chat_history, query)

        logger.info(f"Extracted context: {json.dumps(extracted, ensure_ascii=False)}")

        # Обновить состояние сессии
        state = self.state_manager.update_state(session_id, extracted)

        logger.info(f"Updated state: {state.get_summary()}")

        return state

    def _create_enriched_context(
        self,
        query: str,
        state: TravelContext
    ) -> Dict[str, Any]:
        """
        Создать обогащённый контекст для planner'а.

        Args:
            query: Запрос пользователя
            state: Состояние сессии

        Returns:
            Словарь с контекстными данными
        """
        context = {
            "original_query": query,
            "travel_context": state.to_dict(),
            "state_summary": state.get_summary()
        }

        # Добавить инфу о недостающих полях
        if not state.is_complete_for_search():
            context["missing_for_search"] = state.get_missing_fields()

        return context

    async def _synthesize_final_answer(
        self,
        query: str,
        execution_result: Any,
        plan: Any
    ) -> str:
        """
        Синтезировать финальный ответ из результатов выполнения.

        Args:
            query: Исходный запрос
            execution_result: Результаты выполнения плана
            plan: План который был выполнен

        Returns:
            Финальный ответ для пользователя
        """
        logger.info("Synthesizing final answer")

        # Собираем все успешные результаты
        data_summary = []

        for step_id, result in execution_result.results.items():
            if result.success and result.data:
                data_summary.append({
                    "step_id": step_id,
                    "data": result.data
                })

        # Сериализуем данные в JSON строку
        data_json = json.dumps(data_summary, ensure_ascii=False, indent=2)

        # Формируем промпт для синтеза (используем переменные вместо f-string)
        synthesis_prompt = """Ты - Travel Agent. Сформируй дружелюбный и полезный ответ для пользователя.

ЗАПРОС ПОЛЬЗОВАТЕЛЯ:
{query}

ЦЕЛЬ ПЛАНА:
{goal}

СОБРАННЫЕ ДАННЫЕ:
{data}

ЗАДАЧА:
Создай краткий, информативный и дружелюбный ответ. Включи все важные детали.
Если есть погода - упомяни её. Если есть рейсы - покажи варианты.
Используй эмодзи для лучшей читаемости (но не переборщи).

ОТВЕТ:"""

        from langchain.prompts import ChatPromptTemplate
        prompt = ChatPromptTemplate.from_template(synthesis_prompt)
        messages = prompt.format_messages(
            query=query,
            goal=plan.goal,
            data=data_json
        )

        response = await self.llm.ainvoke(messages)

        return response.content.strip()

    async def process_query(
        self,
        query: str,
        session_id: Optional[str] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Главный метод обработки запроса с context management.

        Pipeline:
        1. Router → определить тип (simple/agent)
        2. Если simple → прямой ответ
        3. Если agent:
           a. Extract context → извлечь сущности из истории
           b. Classify intent → определить намерение пользователя
           c. Check completeness → проверить достаточно ли данных
           d. Если нужны данные → запросить у пользователя
           e. Если context_update → подтвердить и выйти
           f. Planner → создать план с обогащённым контекстом
           g. Yield план пользователю
           h. Orchestrator → выполнить параллельно
           i. Yield прогресс выполнения
           j. Reflector → проверить результаты
           k. Если needs_replan → goto 3f
           l. Yield финальный ответ

        Args:
            query: Запрос пользователя
            session_id: ID сессии

        Yields:
            События выполнения (для SSE streaming)
        """
        session_id = session_id or f"session_{datetime.now().timestamp()}"

        logger.info(f"=== Processing query: {query[:100]} ===")
        logger.info(f"Session ID: {session_id}")

        # Event: start
        yield {
            "event": "start",
            "data": {
                "query": query,
                "session_id": session_id,
                "architecture": "plan-and-execute"
            }
        }

        try:
            # 1. ROUTING
            yield {"event": "routing_start", "data": {"query": query}}

            route_decision = await self.router.route(query)

            yield {
                "event": "routing_complete",
                "data": {
                    "route_type": route_decision.route_type,
                    "confidence": route_decision.confidence,
                    "reasoning": route_decision.reasoning
                }
            }

            # 2. SIMPLE ROUTE
            if route_decision.route_type == RouteType.SIMPLE:
                logger.info("Simple route - returning direct answer")

                yield {
                    "event": "simple_answer",
                    "data": {
                        "answer": route_decision.direct_answer
                    }
                }

                # Save to memory
                memory = self._get_memory(session_id)
                memory.save_context(
                    {"input": query},
                    {"output": route_decision.direct_answer}
                )

                yield {"event": "done", "data": {"type": "simple"}}
                return

            # 3. AGENT ROUTE - Plan and Execute
            logger.info("Agent route - starting plan-and-execute")

            # Get memory and extract context
            memory = self._get_memory(session_id)

            # Extract context from conversation history
            state = await self._extract_and_update_context(query, session_id, memory)

            yield {
                "event": "context_extracted",
                "data": {
                    "state_summary": state.get_summary(),
                    "is_complete": state.is_complete_for_search()
                }
            }

            # Classify intent
            intent = self.intent_classifier.classify_intent(query, state)
            logger.info(f"Detected intent: {intent}")

            yield {
                "event": "intent_detected",
                "data": {"intent": intent}
            }

            # Check if we have enough context for the intent
            is_complete, missing_fields = self.intent_classifier.check_completeness(intent, state)

            if not is_complete and intent == 'flight_search':
                # Need more information for flight search
                missing_ru = []
                for field in missing_fields:
                    if field == 'origin':
                        missing_ru.append('город вылета')
                    elif field == 'destination':
                        missing_ru.append('город назначения')
                    elif field == 'departure_date':
                        missing_ru.append('дату вылета')

                response_text = f"Для поиска рейсов мне нужно уточнить: {', '.join(missing_ru)}."

                yield {
                    "event": "need_more_info",
                    "data": {
                        "message": response_text,
                        "missing_fields": missing_fields
                    }
                }

                memory.save_context(
                    {"input": query},
                    {"output": response_text}
                )

                yield {"event": "done", "data": {"type": "need_info"}}
                return

            # Handle context_update intent (short clarifications)
            if intent == 'context_update':
                response_text = f"Понял! {state.get_summary()}. Чем ещё могу помочь?"

                yield {
                    "event": "context_update_acknowledged",
                    "data": {"message": response_text, "state": state.to_dict()}
                }

                memory.save_context(
                    {"input": query},
                    {"output": response_text}
                )

                yield {"event": "done", "data": {"type": "context_update"}}
                return

            # Create enriched context for planner
            context = self._create_enriched_context(query, state)

            # Replan loop
            max_replans = 2
            replan_count = 0

            while replan_count <= max_replans:
                # 3a. PLANNING
                yield {"event": "planning_start", "data": {"attempt": replan_count + 1}}

                plan = await self.planner.create_plan(query, context=context)

                yield {
                    "event": "plan_created",
                    "data": {
                        "goal": plan.goal,
                        "steps": [
                            {
                                "id": step.id,
                                "description": step.description,
                                "action": step.action,
                                "params": step.params,
                                "can_parallel": step.can_parallel,
                                "depends_on": step.depends_on,
                                "estimated_time": step.estimated_time_sec
                            }
                            for step in plan.steps
                        ],
                        "total_estimated_time": plan.total_estimated_time,
                        "replan_attempt": replan_count
                    }
                }

                # 3b. EXECUTION
                yield {"event": "execution_start", "data": {"plan_id": id(plan)}}

                # Execute plan without callback (we'll handle events separately)
                execution_result = await self.orchestrator.execute_plan(plan)

                yield {
                    "event": "execution_complete",
                    "data": {
                        "success": execution_result.success,
                        "total_time": execution_result.total_execution_time,
                        "errors_count": len(execution_result.errors)
                    }
                }

                # 3c. REFLECTION
                yield {"event": "reflection_start", "data": {}}

                reflection = await self.reflector.reflect(
                    query,
                    plan,
                    execution_result,
                    replan_count=replan_count
                )

                yield {
                    "event": "reflection_complete",
                    "data": {
                        "status": reflection.status,
                        "assessment": reflection.assessment,
                        "suggestions": reflection.suggestions,
                        "confidence": reflection.confidence
                    }
                }

                # 3d. DECIDE NEXT ACTION
                if reflection.status == ReflectionStatus.SUCCESS:
                    # SUCCESS - формируем финальный ответ
                    logger.info("Reflection: SUCCESS - generating final answer")

                    final_answer = await self._synthesize_final_answer(
                        query,
                        execution_result,
                        plan
                    )

                    yield {
                        "event": "final_answer",
                        "data": {"answer": final_answer}
                    }

                    # Save to memory
                    memory.save_context(
                        {"input": query},
                        {"output": final_answer}
                    )

                    yield {"event": "done", "data": {"type": "success"}}
                    break

                elif reflection.status == ReflectionStatus.NEEDS_USER_INPUT:
                    # Нужна информация от пользователя
                    logger.info("Reflection: NEEDS_USER_INPUT")

                    yield {
                        "event": "needs_user_input",
                        "data": {
                            "questions": reflection.suggestions,
                            "assessment": reflection.assessment
                        }
                    }

                    yield {"event": "done", "data": {"type": "needs_input"}}
                    break

                elif reflection.status == ReflectionStatus.NEEDS_REPLAN:
                    # Нужен replan
                    replan_count += 1

                    if replan_count > max_replans:
                        logger.warning(f"Max replans ({max_replans}) reached")

                        # Формируем ответ из того что есть
                        final_answer = await self._synthesize_final_answer(
                            query,
                            execution_result,
                            plan
                        )

                        yield {
                            "event": "final_answer",
                            "data": {
                                "answer": final_answer,
                                "note": "Достигнут лимит replans, используем имеющиеся данные"
                            }
                        }

                        yield {"event": "done", "data": {"type": "max_replans"}}
                        break

                    logger.info(f"Reflection: NEEDS_REPLAN (attempt {replan_count + 1})")

                    yield {
                        "event": "replan",
                        "data": {
                            "reason": reflection.assessment,
                            "suggestions": reflection.suggestions,
                            "attempt": replan_count + 1
                        }
                    }

                    # Продолжаем цикл (создаём новый план)
                    continue

        except Exception as e:
            logger.error(f"Error processing query: {e}", exc_info=True)

            yield {
                "event": "error",
                "data": {
                    "error": str(e),
                    "type": type(e).__name__
                }
            }

    def shutdown(self):
        """Cleanup resources."""
        logger.info("Shutting down TravelAgent")
        self.orchestrator.shutdown()


# ============================================================================
# MAIN (для тестирования)
# ============================================================================

if __name__ == "__main__":
    import asyncio

    async def test_agent():
        """Test the agent"""
        agent = TravelAgent()

        print("Testing Travel Agent V2 (Plan-and-Execute)...\n")

        # Test queries
        queries = [
            "Найди рейсы из Москвы в Париж на 20 января",
            # "Спланируй поездку в Берлин",  # Должен спросить город вылета
            # "Какая погода в Токио?",  # Только погода
        ]

        for query in queries:
            print(f"\n{'='*60}")
            print(f"Query: {query}")
            print('='*60)

            async for event in agent.process_query(query):
                event_type = event["event"]
                data = event.get("data", {})

                if event_type == "plan_created":
                    print(f"\n📋 PLAN CREATED:")
                    print(f"  Goal: {data['goal']}")
                    print(f"  Steps ({len(data['steps'])}):")
                    for step in data["steps"]:
                        print(f"    {step['id']}. {step['description']} (parallel={step['can_parallel']})")

                elif event_type == "step_started":
                    print(f"  ▶️  Step {data.get('step_id')}: {data.get('data', {}).get('description', 'N/A')}")

                elif event_type == "step_completed":
                    status = "✅" if data.get("success") else "❌"
                    print(f"  {status} Step {data.get('step_id')}: {data.get('execution_time', 0):.2f}s")

                elif event_type == "final_answer":
                    print(f"\n💬 FINAL ANSWER:")
                    print(f"{data['answer']}\n")

                elif event_type == "needs_user_input":
                    print(f"\n❓ NEEDS USER INPUT:")
                    for q in data.get("questions", []):
                        print(f"  - {q}")

        agent.shutdown()

    # Run test
    asyncio.run(test_agent())
