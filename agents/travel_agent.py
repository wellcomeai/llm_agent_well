"""
Travel Agent with OpenAI and ReAct Pattern.

This agent helps users plan trips by:
1. Getting weather information for destinations
2. Searching for flights
3. Providing travel recommendations

Uses ReAct pattern: Think → Act → Observe → Repeat
"""

import os
import json
import logging
from datetime import datetime
from typing import AsyncGenerator, Dict, Any, Optional
from openai import AsyncOpenAI

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import our custom functions
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from functions.weather import get_weather
from functions.flights import search_flights


# System instructions with explicit ReAct pattern
SYSTEM_INSTRUCTIONS = """
Ты - профессиональный помощник по планированию путешествий (Travel Agent).

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
   - НЕ делай все действия сразу!

2. ACT (Действие):
   - Выполни ОДНО действие из плана
   - Вызови соответствующий инструмент (get_weather или search_flights)
   - Подожди результата

3. OBSERVE (Наблюдение):
   - Проанализируй полученный результат
   - Определи, достаточно ли информации
   - Реши, нужны ли дополнительные действия

4. REPEAT (Повтор):
   - Если нужно больше информации - вернись к шагу THINK
   - Если информации достаточно - переходи к DONE

5. DONE (Завершение):
   - Сформулируй итоговый ответ пользователю
   - Включи всю собранную информацию
   - Дай полезные рекомендации

**Правила:**
- НЕ вызывай все функции сразу
- Делай шаги последовательно
- Если информации недостаточно - спрашивай у пользователя
- Всегда объясняй свои рассуждения
- Будь дружелюбным и полезным
- Отвечай на русском языке (но города называй по-английски для API)
"""


class TravelAgent:
    """
    Travel Agent using OpenAI with ReAct pattern.
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
        logger.info("=== Initializing TravelAgent (OpenAI) ===")
        
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            logger.error("OPENAI_API_KEY not found in environment")
            raise ValueError("OPENAI_API_KEY не найден в environment variables")

        self.model_name = model_name
        self.temperature = temperature
        self.max_tokens = max_tokens

        logger.info(f"Model: {model_name}, Temperature: {temperature}")

        # Initialize OpenAI client
        try:
            self.client = AsyncOpenAI(api_key=self.api_key)
            logger.info("OpenAI client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize OpenAI client: {e}")
            raise

        # Define tools for the agent (OpenAI format)
        self.tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "Получает текущую погоду для указанного города. Возвращает температуру, описание, влажность, ветер.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "city": {
                                "type": "string",
                                "description": "Название города на английском (например: Paris, London, Amsterdam)"
                            }
                        },
                        "required": ["city"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "search_flights",
                    "description": "Ищет доступные рейсы между двумя городами. Возвращает список рейсов с ценами, временем вылета/прилета, продолжительностью.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "from_city": {
                                "type": "string",
                                "description": "Город вылета на английском (например: Amsterdam, London)"
                            },
                            "to_city": {
                                "type": "string",
                                "description": "Город прилета на английском (например: Paris, Berlin)"
                            },
                            "date": {
                                "type": "string",
                                "description": "Дата вылета в формате YYYY-MM-DD. Необязательный параметр, по умолчанию завтра."
                            }
                        },
                        "required": ["from_city", "to_city"]
                    }
                }
            }
        ]

        # Session memory (простая реализация для MVP)
        self.sessions: Dict[str, list] = {}
        
        logger.info("TravelAgent initialization complete")

    def _execute_function(self, function_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a function call.

        Args:
            function_name: Name of the function to call
            arguments: Function arguments

        Returns:
            Function result
        """
        logger.info(f"Executing function: {function_name} with args: {arguments}")
        
        try:
            if function_name == "get_weather":
                result = get_weather(**arguments)
                logger.info(f"get_weather result: {result.get('success', False)}")
                return result
            elif function_name == "search_flights":
                result = search_flights(**arguments)
                logger.info(f"search_flights result: {result.get('success', False)}")
                return result
            else:
                logger.error(f"Unknown function: {function_name}")
                return {
                    "success": False,
                    "error": f"Unknown function: {function_name}"
                }
        except Exception as e:
            logger.error(f"Error executing {function_name}: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Error in {function_name}: {str(e)}"
            }

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
                "step_type": "think" | "act" | "observe" | "done" | "error",
                "content": "step content",
                "timestamp": "ISO timestamp",
                "metadata": {...}
            }
        """
        session_id = session_id or f"session_{datetime.now().timestamp()}"
        
        logger.info(f"=== Starting agent run for session: {session_id} ===")
        logger.info(f"User query: {user_query}")

        # Initialize or get session history
        if session_id not in self.sessions:
            self.sessions[session_id] = [
                {"role": "system", "content": SYSTEM_INSTRUCTIONS}
            ]
            logger.info(f"Created new session: {session_id}")

        # Add user message to history
        self.sessions[session_id].append({
            "role": "user",
            "content": user_query
        })

        try:
            # Yield start event
            logger.info("Yielding START event")
            yield {
                "step_type": "start",
                "content": f"Обрабатываю запрос: {user_query}",
                "timestamp": datetime.now().isoformat(),
                "metadata": {"session_id": session_id}
            }

            # Run ReAct loop
            max_iterations = 10
            iteration = 0

            while iteration < max_iterations:
                iteration += 1
                logger.info(f"=== ReAct iteration {iteration}/{max_iterations} ===")

                try:
                    # Call OpenAI API
                    logger.info("Calling OpenAI API...")
                    response = await self.client.chat.completions.create(
                        model=self.model_name,
                        messages=self.sessions[session_id],
                        tools=self.tools,
                        tool_choice="auto",
                        temperature=self.temperature,
                        max_tokens=self.max_tokens
                    )
                    logger.info("Received response from OpenAI API")

                    message = response.choices[0].message
                    
                    # Add assistant's response to history
                    self.sessions[session_id].append(message.model_dump())

                    # Check if model wants to call a function
                    if message.tool_calls:
                        logger.info(f"Model requested {len(message.tool_calls)} tool call(s)")
                        
                        for tool_call in message.tool_calls:
                            function_name = tool_call.function.name
                            function_args = json.loads(tool_call.function.arguments)

                            logger.info(f"Tool call: {function_name}")

                            # Yield ACT step
                            yield {
                                "step_type": "act",
                                "content": f"Вызываю функцию: {function_name}",
                                "timestamp": datetime.now().isoformat(),
                                "metadata": {
                                    "tool_name": function_name,
                                    "tool_args": function_args
                                }
                            }

                            # Execute function
                            function_result = self._execute_function(function_name, function_args)

                            # Yield OBSERVE step
                            yield {
                                "step_type": "observe",
                                "content": f"Результат функции {function_name}: {json.dumps(function_result, ensure_ascii=False, indent=2)}",
                                "timestamp": datetime.now().isoformat(),
                                "metadata": {
                                    "tool_name": function_name,
                                    "tool_result": function_result
                                }
                            }

                            # Add function result to history
                            self.sessions[session_id].append({
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "name": function_name,
                                "content": json.dumps(function_result, ensure_ascii=False)
                            })

                    else:
                        # Model has generated final text response
                        final_text = message.content
                        logger.info(f"Model generated final response (length: {len(final_text) if final_text else 0})")

                        # Yield DONE step
                        yield {
                            "step_type": "done",
                            "content": final_text or "Ответ получен",
                            "timestamp": datetime.now().isoformat(),
                            "metadata": {
                                "iterations": iteration,
                                "session_id": session_id
                            }
                        }

                        logger.info("Agent completed successfully")
                        break

                except Exception as e:
                    logger.error(f"Error in ReAct iteration {iteration}: {e}", exc_info=True)
                    yield {
                        "step_type": "error",
                        "content": f"Ошибка в итерации {iteration}: {str(e)}",
                        "timestamp": datetime.now().isoformat(),
                        "metadata": {
                            "error_type": type(e).__name__,
                            "iteration": iteration
                        }
                    }
                    break

            if iteration >= max_iterations:
                logger.warning("Reached max iterations")
                yield {
                    "step_type": "error",
                    "content": "Достигнут лимит итераций ReAct loop",
                    "timestamp": datetime.now().isoformat(),
                    "metadata": {"max_iterations": max_iterations}
                }

        except Exception as e:
            logger.error(f"Fatal error in agent.run(): {e}", exc_info=True)
            yield {
                "step_type": "error",
                "content": f"Ошибка при обработке запроса: {str(e)}",
                "timestamp": datetime.now().isoformat(),
                "metadata": {"error_type": type(e).__name__}
            }


if __name__ == "__main__":
    import asyncio

    async def test_agent():
        """Test the agent"""
        agent = TravelAgent()

        print("Testing Travel Agent with ReAct pattern...\n")

        # Test query
        query = "Какая погода в Париже?"

        print(f"User: {query}\n")

        async for step in agent.run(query):
            print(f"[{step['step_type'].upper()}] {step['content']}\n")

    # Run test
    asyncio.run(test_agent())
