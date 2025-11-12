"""
Travel Agent with LangChain and ReAct Pattern.

This agent helps users plan trips by:
1. Getting weather information for destinations
2. Searching for flights
3. Providing travel recommendations

Uses LangChain's built-in ReAct agent with streaming callbacks.
"""

import os
import logging
import asyncio
import json
from datetime import datetime
from typing import AsyncGenerator, Dict, Any, Optional

from langchain.agents import create_react_agent, AgentExecutor
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.memory import ConversationSummaryBufferMemory
from langchain.callbacks.base import AsyncCallbackHandler
from dotenv import load_dotenv

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import our custom tools
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from functions.weather import get_weather_tool
from functions.flights import search_flights_tool

load_dotenv()


# ============================================================================
# REACT PROMPT TEMPLATE
# ============================================================================

REACT_PROMPT = """Ты - профессиональный помощник по планированию путешествий (Travel Agent).

Твоя роль:
- Помогать пользователям планировать поездки
- Получать информацию о погоде в городах назначения
- Искать подходящие рейсы
- Давать полезные рекомендации для путешественников

ВАЖНО: Ты используешь ReAct паттерн (Reasoning and Acting):

**ReAct Pattern Flow:**

1. THINK (Размышление):
   - Проанализируй запрос пользователя
   - Определи, какую информацию нужно собрать
   - Составь пошаговый план действий

2. ACT (Действие):
   - Выполни ОДНО действие из плана
   - Вызови соответствующий инструмент
   - Подожди результата

3. OBSERVE (Наблюдение):
   - Проанализируй полученный результат
   - Определи, достаточно ли информации
   - Реши, нужны ли дополнительные действия

4. REPEAT (Повтор):
   - Если нужно больше информации - повтори цикл
   - Если информации достаточно - переходи к финальному ответу

**Правила:**
- Делай шаги последовательно, НЕ вызывай все функции сразу
- Если информации недостаточно - спрашивай у пользователя
- Всегда объясняй свои рассуждения
- Будь дружелюбным и полезным
- Отвечай на русском языке (но города называй по-английски для API)
- Давай конкретные рекомендации на основе полученных данных

Доступные инструменты:
{tools}

Используй следующий формат:

Thought: [твои размышления о том, что нужно сделать]
Action: [название инструмента из списка выше]
Action Input: [входные данные для инструмента в формате JSON]
Observation: [результат выполнения инструмента]
... (повторяй Thought/Action/Action Input/Observation сколько нужно)
Thought: Теперь у меня есть вся необходимая информация для ответа
Final Answer: [подробный и полезный ответ пользователю на русском языке]

Начинай!

{agent_scratchpad}"""


# ============================================================================
# STREAMING CALLBACK FOR SSE
# ============================================================================

class TravelAgentStreamingCallback(AsyncCallbackHandler):
    """
    Async callback handler для streaming шагов агента в SSE формате.

    Генерирует события:
    - act: когда агент вызывает инструмент
    - observe: когда инструмент возвращает результат
    - done: когда агент завершил работу
    - error: при ошибках
    """

    def __init__(self, queue: asyncio.Queue):
        """
        Args:
            queue: Asyncio Queue для передачи событий
        """
        self.queue = queue
        logger.info("TravelAgentStreamingCallback initialized")

    async def on_agent_action(self, action, **kwargs):
        """
        Вызывается когда агент решает вызвать инструмент.

        Args:
            action: AgentAction объект с информацией о вызове
        """
        logger.info(f"Agent action: {action.tool}")

        await self.queue.put({
            "step_type": "act",
            "content": f"Вызываю функцию: {action.tool}",
            "timestamp": datetime.now().isoformat(),
            "metadata": {
                "tool_name": action.tool,
                "tool_input": action.tool_input
            }
        })

    async def on_tool_end(self, output: str, **kwargs):
        """
        Вызывается когда инструмент возвращает результат.

        Args:
            output: Результат выполнения инструмента (JSON строка)
        """
        logger.info("Tool execution completed")

        # Парсим JSON результат для metadata
        try:
            result_dict = json.loads(output)
            success = result_dict.get("success", True)

            if success:
                content = "Результат получен успешно"
            else:
                content = f"Получена ошибка: {result_dict.get('error', 'Unknown')}"
        except json.JSONDecodeError:
            result_dict = {"raw_output": output}
            content = "Результат получен"

        await self.queue.put({
            "step_type": "observe",
            "content": content,
            "timestamp": datetime.now().isoformat(),
            "metadata": {"tool_result": result_dict}
        })

    async def on_agent_finish(self, finish, **kwargs):
        """
        Вызывается когда агент закончил работу и готов дать финальный ответ.

        Args:
            finish: AgentFinish объект с финальным ответом
        """
        logger.info("Agent finished successfully")

        final_output = finish.return_values.get("output", "Ответ получен")

        await self.queue.put({
            "step_type": "done",
            "content": final_output,
            "timestamp": datetime.now().isoformat(),
            "metadata": {"completed": True}
        })

    async def on_chain_error(self, error: Exception, **kwargs):
        """
        Вызывается при ошибке в chain/agent.

        Args:
            error: Exception объект
        """
        logger.error(f"Chain error: {error}", exc_info=True)

        await self.queue.put({
            "step_type": "error",
            "content": f"Ошибка: {str(error)}",
            "timestamp": datetime.now().isoformat(),
            "metadata": {
                "error_type": type(error).__name__,
                "error_message": str(error)
            }
        })


# ============================================================================
# TRAVEL AGENT CLASS
# ============================================================================

class TravelAgent:
    """
    Travel Agent using LangChain with ReAct pattern.

    Features:
    - Built-in ReAct agent with create_react_agent()
    - ConversationSummaryBufferMemory for session management
    - Async streaming callbacks for SSE
    - Proper error handling
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: str = "gpt-4o-mini",
        temperature: float = 0.7,
        max_tokens: int = 2000
    ):
        """
        Initialize the Travel Agent.

        Args:
            api_key: OpenAI API key (если None, берется из env OPENAI_API_KEY)
            model_name: Model name to use
            temperature: Model temperature (0.0-1.0)
            max_tokens: Maximum tokens in response
        """
        logger.info("=== Initializing TravelAgent (LangChain) ===")

        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            logger.error("OPENAI_API_KEY not found in environment")
            raise ValueError("OPENAI_API_KEY не найден в environment variables")

        self.model_name = model_name
        self.temperature = temperature
        self.max_tokens = max_tokens

        logger.info(f"Model: {model_name}, Temperature: {temperature}")

        # Initialize LLM
        try:
            self.llm = ChatOpenAI(
                model=model_name,
                temperature=temperature,
                max_tokens=max_tokens,
                streaming=True,  # Enable streaming
                api_key=self.api_key
            )
            logger.info("ChatOpenAI initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize ChatOpenAI: {e}")
            raise

        # Define tools
        self.tools = [get_weather_tool, search_flights_tool]
        logger.info(f"Tools loaded: {[tool.name for tool in self.tools]}")

        # Create prompt template
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", REACT_PROMPT),
            MessagesPlaceholder(variable_name="chat_history", optional=True),
            ("human", "{input}"),
            ("ai", "{agent_scratchpad}")
        ])
        logger.info("Prompt template created")

        # Create ReAct agent
        try:
            self.agent = create_react_agent(
                llm=self.llm,
                tools=self.tools,
                prompt=self.prompt
            )
            logger.info("ReAct agent created successfully")
        except Exception as e:
            logger.error(f"Failed to create ReAct agent: {e}")
            raise

        # Session memories storage
        self.memories: Dict[str, ConversationSummaryBufferMemory] = {}
        logger.info("TravelAgent initialization complete")

    def _get_memory(self, session_id: str) -> ConversationSummaryBufferMemory:
        """
        Get or create memory for a session.

        Uses ConversationSummaryBufferMemory which:
        - Keeps recent messages in buffer
        - Summarizes older messages to save tokens
        - Balances context and token usage

        Args:
            session_id: Session identifier

        Returns:
            ConversationSummaryBufferMemory instance
        """
        if session_id not in self.memories:
            logger.info(f"Creating new memory for session: {session_id}")

            self.memories[session_id] = ConversationSummaryBufferMemory(
                llm=self.llm,
                max_token_limit=1000,  # Summarize when exceeds
                memory_key="chat_history",
                return_messages=True,
                input_key="input",
                output_key="output"
            )

        return self.memories[session_id]

    async def run(
        self,
        user_query: str,
        session_id: Optional[str] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Run the agent with streaming ReAct loop.

        Args:
            user_query: User's question or request
            session_id: Optional session ID for memory

        Yields:
            Step dictionaries with ReAct loop progress:
            {
                "step_type": "start" | "act" | "observe" | "done" | "error",
                "content": "step content",
                "timestamp": "ISO timestamp",
                "metadata": {...}
            }
        """
        session_id = session_id or f"session_{datetime.now().timestamp()}"

        logger.info(f"=== Starting agent run for session: {session_id} ===")
        logger.info(f"User query: {user_query}")

        # Yield start event
        logger.info("Yielding START event")
        yield {
            "step_type": "start",
            "content": f"Обрабатываю запрос: {user_query}",
            "timestamp": datetime.now().isoformat(),
            "metadata": {"session_id": session_id}
        }

        # Setup streaming
        queue = asyncio.Queue()
        callback = TravelAgentStreamingCallback(queue)

        # Get memory for session
        memory = self._get_memory(session_id)

        # Create agent executor
        executor = AgentExecutor(
            agent=self.agent,
            tools=self.tools,
            memory=memory,
            verbose=True,
            handle_parsing_errors=True,
            max_iterations=10,
            return_intermediate_steps=True
        )

        logger.info("AgentExecutor created, starting execution...")

        # Run agent in background task
        task = asyncio.create_task(
            executor.ainvoke(
                {"input": user_query},
                config={"callbacks": [callback]}
            )
        )

        # Stream events from queue
        while not task.done() or not queue.empty():
            try:
                # Wait for event with timeout
                step = await asyncio.wait_for(queue.get(), timeout=0.1)
                logger.debug(f"Yielding step: {step['step_type']}")
                yield step
            except asyncio.TimeoutError:
                # No event yet, continue waiting
                continue
            except Exception as e:
                logger.error(f"Error in streaming loop: {e}", exc_info=True)
                yield {
                    "step_type": "error",
                    "content": f"Ошибка streaming: {str(e)}",
                    "timestamp": datetime.now().isoformat(),
                    "metadata": {"error_type": type(e).__name__}
                }
                break

        # Check if task completed successfully
        try:
            result = await task
            logger.info(f"Agent execution completed successfully")
        except Exception as e:
            logger.error(f"Agent execution failed: {e}", exc_info=True)
            yield {
                "step_type": "error",
                "content": f"Ошибка при обработке запроса: {str(e)}",
                "timestamp": datetime.now().isoformat(),
                "metadata": {"error_type": type(e).__name__}
            }


# ============================================================================
# MAIN (для тестирования)
# ============================================================================

if __name__ == "__main__":
    import asyncio

    async def test_agent():
        """Test the agent"""
        agent = TravelAgent()

        print("Testing Travel Agent with LangChain ReAct pattern...\n")

        # Test query
        query = "Какая погода в Париже?"

        print(f"User: {query}\n")

        async for step in agent.run(query):
            print(f"[{step['step_type'].upper()}] {step['content']}\n")

    # Run test
    asyncio.run(test_agent())
