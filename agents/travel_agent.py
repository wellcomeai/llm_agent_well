"""
Travel Agent with Google ADK and ReAct Pattern.

This agent helps users plan trips by:
1. Getting weather information for destinations
2. Searching for flights
3. Providing travel recommendations

Uses ReAct pattern: Think → Act → Observe → Repeat
"""

import os
import json
from datetime import datetime
from typing import AsyncGenerator, Dict, Any, Optional
from google import genai
from google.genai.types import Tool, GenerateContentConfig, Content, Part

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

**Пример работы:**

User: "Хочу полететь в Париж на выходные"

THINK: "Мне нужно узнать:
1. Погоду в Париже (чтобы рекомендовать что взять)
2. Откуда пользователь хочет лететь (это не указано!)
План: сначала узнаю погоду, потом спрошу про город вылета"

ACT: Вызываю get_weather("Paris")

OBSERVE: "Погода получена: +15°C, облачно. Хорошая информация.
Но я не знаю откуда пользователь летит - нужно спросить."

DONE: "В Париже сейчас +15°C, облачно - отличная погода для прогулок!
Из какого города вы планируете вылет, чтобы я мог найти рейсы?"

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
    Travel Agent using Google ADK with ReAct pattern.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: str = "gemini-2.0-flash-exp",
        temperature: float = 0.7,
        max_tokens: int = 2000
    ):
        """
        Initialize the Travel Agent.

        Args:
            api_key: Google API key (если None, берется из env GOOGLE_API_KEY)
            model_name: Model name to use
            temperature: Model temperature (0.0-1.0)
            max_tokens: Maximum tokens in response
        """
        self.api_key = api_key or os.getenv("GOOGLE_API_KEY")
        if not self.api_key:
            raise ValueError("GOOGLE_API_KEY не найден в environment variables")

        self.model_name = model_name
        self.temperature = temperature
        self.max_tokens = max_tokens

        # Initialize Google GenAI client
        self.client = genai.Client(api_key=self.api_key)

        # Define tools for the agent
        self.tools = [
            Tool(function_declarations=[
                {
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
                },
                {
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
            ])
        ]

        # Session memory (простая реализация для MVP)
        self.sessions: Dict[str, list] = {}

    def _execute_function(self, function_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a function call.

        Args:
            function_name: Name of the function to call
            arguments: Function arguments

        Returns:
            Function result
        """
        if function_name == "get_weather":
            return get_weather(**arguments)
        elif function_name == "search_flights":
            return search_flights(**arguments)
        else:
            return {
                "success": False,
                "error": f"Unknown function: {function_name}"
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

        # Initialize or get session history
        if session_id not in self.sessions:
            self.sessions[session_id] = []

        # Add user message to history
        self.sessions[session_id].append({
            "role": "user",
            "parts": [{"text": user_query}]
        })

        try:
            # Yield start event
            yield {
                "step_type": "start",
                "content": f"Обрабатываю запрос: {user_query}",
                "timestamp": datetime.now().isoformat(),
                "metadata": {"session_id": session_id}
            }

            # Create config
            config = GenerateContentConfig(
                temperature=self.temperature,
                max_output_tokens=self.max_tokens,
                system_instruction=SYSTEM_INSTRUCTIONS,
            )

            # Run ReAct loop
            max_iterations = 10
            iteration = 0

            while iteration < max_iterations:
                iteration += 1

                # Generate response
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=self.sessions[session_id],
                    config=config,
                    tools=self.tools
                )

                # Check if model wants to call a function
                if response.candidates[0].content.parts[0].function_call:
                    function_call = response.candidates[0].content.parts[0].function_call
                    function_name = function_call.name
                    function_args = dict(function_call.args)

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

                    # Add function call to history
                    self.sessions[session_id].append({
                        "role": "model",
                        "parts": [{"function_call": function_call}]
                    })

                    # Add function response to history
                    self.sessions[session_id].append({
                        "role": "user",
                        "parts": [{
                            "function_response": {
                                "name": function_name,
                                "response": function_result
                            }
                        }]
                    })

                else:
                    # Model has generated final text response
                    final_text = response.candidates[0].content.parts[0].text

                    # Add to history
                    self.sessions[session_id].append({
                        "role": "model",
                        "parts": [{"text": final_text}]
                    })

                    # Yield DONE step
                    yield {
                        "step_type": "done",
                        "content": final_text,
                        "timestamp": datetime.now().isoformat(),
                        "metadata": {
                            "iterations": iteration,
                            "session_id": session_id
                        }
                    }

                    break

            if iteration >= max_iterations:
                yield {
                    "step_type": "error",
                    "content": "Достигнут лимит итераций ReAct loop",
                    "timestamp": datetime.now().isoformat(),
                    "metadata": {"max_iterations": max_iterations}
                }

        except Exception as e:
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
