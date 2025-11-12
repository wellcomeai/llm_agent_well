"""
ReAct Agent для гибких исследовательских задач.

Использует LangChain AgentExecutor с ReAct паттерном для обработки
открытых запросов, требующих гибкости и адаптации на ходу.
"""

import logging
import json
from typing import List, Dict, Any, AsyncGenerator, Optional
from langchain_openai import ChatOpenAI
from langchain.agents import create_react_agent, AgentExecutor
from langchain.prompts import PromptTemplate
from langchain.tools import Tool
from langchain.schema import AgentAction, AgentFinish
from langchain.callbacks.base import AsyncCallbackHandler

logger = logging.getLogger(__name__)


# ============================================================================
# REACT PROMPT
# ============================================================================

TRAVEL_REACT_PROMPT = """Ты - опытный агент Travel Assistant, работающий по методологии ReAct (Reasoning + Acting).

ДОСТУПНЫЕ ИНСТРУМЕНТЫ:
{tools}

ФОРМАТ ИНСТРУМЕНТОВ:
{tool_names}

Используй следующий формат для каждого шага:

Question: входной вопрос/запрос от пользователя
Thought: обдумай что нужно сделать
Action: инструмент из [{tool_names}]
Action Input: входные данные для инструмента (JSON формат)
Observation: результат выполнения инструмента
... (этот Thought/Action/Action Input/Observation цикл может повторяться N раз)
Thought: Теперь я знаю финальный ответ
Final Answer: финальный ответ пользователю на русском языке

ВАЖНЫЕ ПРАВИЛА:
1. Всегда используй "Thought" перед действием для обдумывания
2. Используй "Action" чтобы вызвать инструмент
3. Используй "Action Input" для передачи параметров в JSON
4. После "Observation" снова используй "Thought" для анализа результата
5. Когда готов ответить, используй "Thought: Теперь я знаю финальный ответ" и "Final Answer"
6. Если информации недостаточно, используй инструменты несколько раз
7. Для исследовательских задач пробуй разные варианты и комбинации

ПРИМЕРЫ:

Пример 1 - Исследование вариантов:
Question: Исследуй варианты отдыха в Юго-Восточной Азии
Thought: Мне нужно проверить погоду в популярных направлениях ЮВА
Action: get_weather
Action Input: {{"city": "Bangkok"}}
Observation: Температура в Бангкоке 32°C, влажность 80%, солнечно
Thought: Бангкок жаркий. Проверю другие варианты
Action: get_weather
Action Input: {{"city": "Hanoi"}}
Observation: Температура в Ханое 25°C, облачно
Thought: Теперь я знаю финальный ответ
Final Answer: В Юго-Восточной Азии сейчас два отличных варианта:
1. Бангкок (Таиланд) - 32°C, солнечно, идеально для пляжного отдыха
2. Ханой (Вьетнам) - 25°C, облачно, комфортно для экскурсий

Пример 2 - Подбор направления:
Question: Подбери что-нибудь интересное в Европе на выходные
Thought: Проверю погоду в нескольких европейских городах
Action: get_weather
Action Input: {{"city": "Paris"}}
Observation: Температура в Париже 12°C, дождливо
Thought: Париж дождливый. Попробую южную Европу
Action: get_weather
Action Input: {{"city": "Barcelona"}}
Observation: Температура в Барселоне 18°C, солнечно
Thought: Теперь я знаю финальный ответ
Final Answer: Рекомендую Барселону для выходных! Сейчас там 18°C и солнечно, идеально для прогулок по городу и пляжу.

ТЕКУЩИЙ ЗАПРОС:
Question: {input}
{agent_scratchpad}"""


# ============================================================================
# STREAMING CALLBACK
# ============================================================================

class ReActStreamingCallback(AsyncCallbackHandler):
    """
    Callback для streaming событий ReAct агента.
    Генерирует события для SSE (Server-Sent Events).
    """

    def __init__(self):
        super().__init__()
        self.current_thought = ""

    async def on_agent_action(self, action: AgentAction, **kwargs) -> None:
        """Вызывается когда агент выбирает действие."""
        logger.info(f"ReAct Action: {action.tool} with input: {action.tool_input}")

    async def on_agent_finish(self, finish: AgentFinish, **kwargs) -> None:
        """Вызывается когда агент завершает работу."""
        logger.info(f"ReAct Finish: {finish.return_values}")

    async def on_tool_start(self, serialized: Dict[str, Any], input_str: str, **kwargs) -> None:
        """Вызывается когда начинается выполнение инструмента."""
        tool_name = serialized.get("name", "unknown")
        logger.info(f"ReAct Tool Start: {tool_name}")

    async def on_tool_end(self, output: str, **kwargs) -> None:
        """Вызывается когда инструмент завершает работу."""
        logger.info(f"ReAct Tool End: {output[:100]}...")


# ============================================================================
# TRAVEL REACT AGENT
# ============================================================================

class TravelReActAgent:
    """
    ReAct Agent для Travel Assistant.

    Использует ReAct паттерн (Reasoning + Acting) для гибкой обработки
    исследовательских и открытых запросов, требующих адаптации на ходу.
    """

    def __init__(
        self,
        llm: ChatOpenAI,
        tools: List[Tool],
        max_iterations: int = 15,
        max_execution_time: Optional[float] = None,
        verbose: bool = True
    ):
        """
        Initialize ReAct Agent.

        Args:
            llm: Language model
            tools: List of available tools
            max_iterations: Maximum number of reasoning iterations
            max_execution_time: Maximum execution time in seconds
            verbose: Enable verbose logging
        """
        self.llm = llm
        self.tools = tools
        self.max_iterations = max_iterations
        self.max_execution_time = max_execution_time
        self.verbose = verbose

        # Создаём prompt template
        self.prompt = PromptTemplate(
            template=TRAVEL_REACT_PROMPT,
            input_variables=["input", "agent_scratchpad"],
            partial_variables={
                "tools": self._format_tools_description(),
                "tool_names": ", ".join([tool.name for tool in tools])
            }
        )

        # Создаём ReAct агента
        self.agent = create_react_agent(
            llm=self.llm,
            tools=self.tools,
            prompt=self.prompt
        )

        # Создаём AgentExecutor
        self.executor = AgentExecutor(
            agent=self.agent,
            tools=self.tools,
            max_iterations=self.max_iterations,
            max_execution_time=self.max_execution_time,
            verbose=self.verbose,
            handle_parsing_errors=True,
            return_intermediate_steps=True
        )

        logger.info(
            f"TravelReActAgent initialized with {len(tools)} tools, "
            f"max_iterations={max_iterations}"
        )

    def _format_tools_description(self) -> str:
        """Форматирование описания инструментов для промпта."""
        descriptions = []
        for tool in self.tools:
            desc = f"- {tool.name}: {tool.description}"
            descriptions.append(desc)
        return "\n".join(descriptions)

    async def run(
        self,
        query: str,
        session_id: str,
        context: Optional[Dict[str, Any]] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Запустить ReAct агента с streaming результатов.

        Args:
            query: Запрос пользователя
            session_id: ID сессии
            context: Дополнительный контекст (опционально)

        Yields:
            Dict с событиями для SSE
        """
        logger.info(f"[{session_id}] Starting ReAct agent for query: {query[:100]}")

        try:
            # Yield начальное событие
            yield {
                "event": "react_start",
                "data": {
                    "query": query,
                    "max_iterations": self.max_iterations
                }
            }

            # Создаём callback для streaming
            callback = ReActStreamingCallback()

            # Запускаем агента
            result = await self.executor.ainvoke(
                {"input": query},
                config={"callbacks": [callback]}
            )

            # Обрабатываем промежуточные шаги
            intermediate_steps = result.get("intermediate_steps", [])

            for i, (action, observation) in enumerate(intermediate_steps, 1):
                # Yield thought (если есть в log)
                if hasattr(action, 'log') and action.log:
                    thought = self._extract_thought_from_log(action.log)
                    if thought:
                        yield {
                            "event": "react_thought",
                            "data": {
                                "step": i,
                                "thought": thought
                            }
                        }

                # Yield action
                yield {
                    "event": "react_action",
                    "data": {
                        "step": i,
                        "tool": action.tool,
                        "tool_input": action.tool_input
                    }
                }

                # Yield observation
                yield {
                    "event": "react_observation",
                    "data": {
                        "step": i,
                        "result": observation
                    }
                }

            # Финальный ответ
            final_answer = result.get("output", "")

            yield {
                "event": "react_complete",
                "data": {
                    "answer": final_answer,
                    "total_steps": len(intermediate_steps)
                }
            }

            logger.info(
                f"[{session_id}] ReAct agent completed in {len(intermediate_steps)} steps"
            )

        except Exception as e:
            logger.error(f"[{session_id}] ReAct agent error: {e}", exc_info=True)

            yield {
                "event": "react_error",
                "data": {
                    "error": str(e),
                    "error_type": type(e).__name__
                }
            }

    def _extract_thought_from_log(self, log: str) -> Optional[str]:
        """
        Извлечь 'Thought' из лога агента.

        Args:
            log: Лог агента

        Returns:
            Извлеченная мысль или None
        """
        try:
            # Ищем строку начинающуюся с "Thought:"
            for line in log.split('\n'):
                if line.strip().startswith('Thought:'):
                    return line.replace('Thought:', '').strip()
            return None
        except Exception as e:
            logger.warning(f"Failed to extract thought: {e}")
            return None


# ============================================================================
# TESTS
# ============================================================================

if __name__ == "__main__":
    """Тестирование ReAct Agent."""
    import asyncio
    import os
    from dotenv import load_dotenv

    load_dotenv()

    async def test_react_agent():
        """Test ReAct agent with mock tools."""
        print("Testing TravelReActAgent...\n")

        # Mock LLM
        llm = ChatOpenAI(
            model="gpt-4o-mini",
            temperature=0.7,
            api_key=os.getenv("OPENAI_API_KEY")
        )

        # Mock tools
        def mock_weather(city: str) -> str:
            """Get weather for a city (mock)."""
            weather_data = {
                "Bangkok": "32°C, солнечно, влажность 80%",
                "Paris": "12°C, дождливо",
                "Barcelona": "18°C, солнечно"
            }
            return weather_data.get(city, f"Погода в {city} неизвестна")

        tools = [
            Tool(
                name="get_weather",
                func=mock_weather,
                description="Получить текущую погоду в городе. Input: city (название города на английском)"
            )
        ]

        # Создаём агента
        agent = TravelReActAgent(
            llm=llm,
            tools=tools,
            max_iterations=5,
            verbose=True
        )

        # Тестовый запрос
        test_query = "Исследуй варианты отдыха в Европе - проверь погоду в Париже и Барселоне"

        print(f"Query: {test_query}\n")
        print("="*60)

        async for event in agent.run(test_query, session_id="test-123"):
            event_type = event.get("event")
            data = event.get("data", {})

            if event_type == "react_start":
                print(f"\n🚀 ReAct Start: {data.get('query')}")

            elif event_type == "react_thought":
                print(f"\n💭 Thought (Step {data.get('step')}): {data.get('thought')}")

            elif event_type == "react_action":
                print(f"🔧 Action: {data.get('tool')} with input: {data.get('tool_input')}")

            elif event_type == "react_observation":
                print(f"👀 Observation: {data.get('result')}")

            elif event_type == "react_complete":
                print(f"\n✅ Complete ({data.get('total_steps')} steps)")
                print(f"📝 Final Answer:\n{data.get('answer')}")

            elif event_type == "react_error":
                print(f"\n❌ Error: {data.get('error')}")

        print("\n" + "="*60)
        print("Test completed!")

    # Run test
    asyncio.run(test_react_agent())
