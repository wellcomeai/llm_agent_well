"""
Travel Agent with LangChain and ReAct Pattern - FIXED VERSION.

Исправления:
1. Улучшенный REACT_PROMPT с чёткими инструкциями
2. Лучший error handling
3. Примеры использования Final Answer
"""

import os
import logging
import asyncio
import json
from datetime import datetime
from typing import AsyncGenerator, Dict, Any, Optional

from langchain.agents import create_react_agent, AgentExecutor
from langchain_openai import ChatOpenAI
from langchain.prompts import PromptTemplate
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
# IMPROVED REACT PROMPT TEMPLATE
# ============================================================================

REACT_PROMPT = """Ты - профессиональный помощник по планированию путешествий (Travel Agent).

КРИТИЧЕСКИ ВАЖНО: Ты МОЖЕШЬ использовать ТОЛЬКО эти инструменты:
{tool_names}

НИКАКИХ других инструментов не существует!

**Твои возможности:**
1. get_weather_tool - узнать погоду в городе (параметр: city)
2. search_flights_tool - найти рейсы между городами (параметры: from_city, to_city, date)
3. Final Answer - дать ответ пользователю

**ВАЖНОЕ ПРАВИЛО:**
- Если тебе нужна информация от пользователя (город вылета, даты и т.д.) → сразу используй "Final Answer" и задай вопрос
- НЕ пытайся придумать несуществующие инструменты!
- НЕ пиши Action с текстом вроде "Ничего не делаю" или "Спрашиваю пользователя"

**Строгий формат ответа:**

Вариант 1 - Использование инструмента:
```
Thought: Мне нужно узнать погоду в Париже
Action: get_weather_tool
Action Input: {{"city": "Paris"}}
```

Вариант 2 - Нужна информация от пользователя:
```
Thought: Мне нужна дополнительная информация от пользователя
Final Answer: Из какого города вы планируете вылететь и на какие даты?
```

Вариант 3 - Готов дать полный ответ:
```
Thought: Теперь у меня есть вся информация для ответа
Final Answer: [Подробный ответ с рекомендациями]
```

**Примеры:**

Пример 1 - Нужна доп. информация:
Вопрос: Спланируй поездку в Берлин на выходные
```
Thought: Чтобы спланировать поездку, мне нужно знать город вылета и точные даты. Сначала узнаю погоду в Берлине.
Action: get_weather_tool
Action Input: {{"city": "Berlin"}}
Observation: {{"success": true, "temperature_c": "18", "description": "Clear"}}
Thought: Погода хорошая (18°C, ясно). Теперь нужна информация от пользователя о городе вылета и датах.
Final Answer: В Берлине отличная погода - 18°C и ясно! 🌤️ 

Чтобы найти подходящие рейсы, уточните, пожалуйста:
• Из какого города вы планируете вылететь?
• На какие конкретно даты? (например, 15-17 января)
```

Пример 2 - Вся информация есть:
Вопрос: Найди рейсы из Москвы в Париж на 15 января
```
Thought: У меня есть все данные: город вылета (Moscow), город прилёта (Paris), дата (2025-01-15). Сначала узнаю погоду в Париже, потом найду рейсы.
Action: get_weather_tool
Action Input: {{"city": "Paris"}}
Observation: {{"success": true, "temperature_c": "12", "description": "Cloudy"}}
Thought: Погода в Париже 12°C, облачно. Теперь найду рейсы.
Action: search_flights_tool
Action Input: {{"from_city": "Moscow", "to_city": "Paris", "date": "2025-01-15"}}
Observation: {{"success": true, "flights": [...]}}
Thought: Отлично, есть рейсы. Могу дать полный ответ.
Final Answer: ✈️ Нашёл рейсы из Москвы в Париж на 15 января:

🌤️ Погода в Париже: 12°C, облачно

Рейсы:
• [детали рейсов из observation]

Рекомендую взять лёгкую куртку - в Париже прохладно!
```

Пример 3 - Только погода:
Вопрос: Какая погода в Токио?
```
Thought: Это простой вопрос о погоде. Использую get_weather_tool.
Action: get_weather_tool
Action Input: {{"city": "Tokyo"}}
Observation: {{"success": true, "temperature_c": "22", "description": "Sunny"}}
Thought: Получил данные о погоде, могу ответить.
Final Answer: В Токио сейчас 22°C, солнечно ☀️ Отличная погода для прогулок!
```

Доступные инструменты:
{tools}

НАЧИНАЙ! Следуй формату строго. Используй Final Answer когда нужна информация от пользователя ИЛИ когда готов дать полный ответ.

Вопрос пользователя: {input}

{agent_scratchpad}"""


# ============================================================================
# STREAMING CALLBACK FOR SSE
# ============================================================================

class TravelAgentStreamingCallback(AsyncCallbackHandler):
    """Async callback handler для streaming шагов агента в SSE формате."""

    def __init__(self, queue: asyncio.Queue):
        self.queue = queue
        logger.info("TravelAgentStreamingCallback initialized")

    async def on_agent_action(self, action, **kwargs):
        """Вызывается когда агент решает вызвать инструмент."""
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
        """Вызывается когда инструмент возвращает результат."""
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
        """Вызывается когда агент закончил работу."""
        logger.info("Agent finished successfully")

        final_output = finish.return_values.get("output", "Ответ получен")

        await self.queue.put({
            "step_type": "done",
            "content": final_output,
            "timestamp": datetime.now().isoformat(),
            "metadata": {"completed": True}
        })

    async def on_chain_error(self, error: Exception, **kwargs):
        """Вызывается при ошибке в chain/agent."""
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
    """Travel Agent using LangChain with ReAct pattern."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: str = "gpt-4o-mini",
        temperature: float = 0.7,
        max_tokens: int = 2000
    ):
        """Initialize the Travel Agent."""
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
                streaming=True,
                api_key=self.api_key
            )
            logger.info("ChatOpenAI initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize ChatOpenAI: {e}")
            raise

        # Define tools
        self.tools = [get_weather_tool, search_flights_tool]
        logger.info(f"Tools loaded: {[tool.name for tool in self.tools]}")

        # Create prompt template for ReAct agent
        self.prompt = PromptTemplate.from_template(REACT_PROMPT)
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
        """Get or create memory for a session."""
        if session_id not in self.memories:
            logger.info(f"Creating new memory for session: {session_id}")

            self.memories[session_id] = ConversationSummaryBufferMemory(
                llm=self.llm,
                max_token_limit=1000,
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
        """Run the agent with streaming ReAct loop."""
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

        # Create agent executor with better error handling
        executor = AgentExecutor(
            agent=self.agent,
            tools=self.tools,
            memory=memory,
            verbose=True,
            handle_parsing_errors=True,  # Обрабатывает ошибки парсинга
            max_iterations=15,  # Увеличил лимит итераций
            return_intermediate_steps=True,
            early_stopping_method="generate"  # Остановка при Final Answer
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
        query = "Спланируй поездку в Берлин на выходные"

        print(f"User: {query}\n")

        async for step in agent.run(query):
            print(f"[{step['step_type'].upper()}] {step['content']}\n")

    # Run test
    asyncio.run(test_agent())
