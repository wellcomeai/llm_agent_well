# 🧳 Travel Agent - Multi-Strategy Router

Интеллектуальный агент-помощник путешествий с **Multi-Strategy Router** и тремя стратегиями обработки запросов.

![Travel Agent Demo](https://img.shields.io/badge/status-Production-green)
![Python](https://img.shields.io/badge/python-3.11+-green)
![Version](https://img.shields.io/badge/version-3.0.0-blue)
![License](https://img.shields.io/badge/license-MIT-blue)

## 🎯 Ключевые возможности

- ✅ **Multi-Strategy Router** - интеллектуальный выбор стратегии обработки
- ✅ **3 стратегии**: Simple, ReAct, Plan-and-Execute
- ✅ **Естественный языковой интерфейс** - общение на русском языке
- ✅ **Real-time SSE Streaming** - наблюдайте за работой агента в реальном времени
- ✅ **Context Management** - извлечение и управление контекстом диалога
- ✅ **Параллельное выполнение** - независимые задачи выполняются одновременно
- ✅ **Инструменты**: получение погоды и поиск рейсов

---

## 🏗️ Архитектура

### Multi-Strategy Router

```
User Query
    ↓
┌─────────────────────────────────────┐
│   MultiStrategyRouter               │
│   (Эвристика + LLM)                 │
└─────────┬───────────────────────────┘
          │
    ┌─────┴────┬──────────────┬─────────┐
    │          │              │         │
    ▼          ▼              ▼         ▼
 SIMPLE     REACT      PLAN_EXECUTE
    │          │              │
    │      (LangChain     (Plan-and-
    │      Agent           Execute
    │      Executor)       Pipeline)
    │          │              │
    └──────────┴──────────────┴─────────►
                    │
                    ▼
              Final Answer
```

### Когда какая стратегия?

| Стратегия | Когда использовать | Примеры |
|-----------|-------------------|---------|
| **SIMPLE** | Вопросы без инструментов, общие знания | "Что такое виза?", "Столица Франции?" |
| **REACT** | Неопределенные, исследовательские задачи | "Исследуй варианты отдыха в Азии", "Подбери что-нибудь интересное" |
| **PLAN_EXECUTE** | Структурированные задачи с четкими шагами | "Найди рейсы из X в Y", "Спланируй: погода + рейсы + отель" |

---

## 📁 Структура проекта

```
llm_agent_well/
│
├── core/                      # Ядро системы
│   ├── models.py              # Pydantic модели (RouteType, Plan, Step, etc.)
│   ├── router.py              # MultiStrategyRouter + IntentClassifier
│   ├── planner.py             # TaskPlanner (создание DAG планов)
│   ├── orchestrator.py        # PlanOrchestrator (параллельное выполнение)
│   ├── reflector.py           # ResultReflector (проверка результатов)
│   ├── state_manager.py       # StateManager (управление TravelContext)
│   └── context_extractor.py   # ContextExtractor (извлечение сущностей)
│
├── agents/                    # Агенты
│   ├── travel_agent.py        # TravelAgent (главный агент с Multi-Strategy)
│   ├── react_agent.py         # TravelReActAgent (ReAct loop)
│   └── legacy_agent.py        # Legacy Google ADK agent
│
├── api/                       # Backend API
│   └── server.py              # FastAPI с SSE streaming
│
├── frontend/                  # Web интерфейс
│   ├── index.html             # Главная страница
│   └── static/                # JS, CSS файлы
│       ├── app_premium.js     # Premium UI с визуализацией
│       └── style_premium.css  # Стили
│
├── functions/                 # Инструменты агента
│   ├── weather.py             # Получение погоды (wttr.in API)
│   └── flights.py             # Поиск рейсов (mock данные)
│
├── requirements.txt           # Python зависимости
├── runtime.txt                # Python версия для деплоя
└── .env.example               # Пример переменных окружения
```

---

## 🚀 Быстрый старт

### 1. Установка зависимостей

```bash
# Клонировать репозиторий
git clone <repo-url>
cd llm_agent_well

# Создать виртуальное окружение
python -m venv venv
source venv/bin/activate  # На Windows: venv\Scripts\activate

# Установить зависимости
pip install -r requirements.txt
```

### 2. Настройка переменных окружения

Создайте файл `.env`:

```bash
# OpenAI API Key (обязательно)
OPENAI_API_KEY=sk-...

# Настройки модели (опционально)
MODEL_NAME=gpt-4o-mini
TEMPERATURE=0.7
MAX_TOKENS=2000
```

### 3. Запуск сервера

```bash
# Запустить FastAPI сервер
uvicorn api.server:app --reload --host 0.0.0.0 --port 8000
```

Откройте в браузере: [http://localhost:8000](http://localhost:8000)

---

## 📊 Детали архитектуры

### 1. SIMPLE Strategy

**Использование:** Простые вопросы без использования инструментов

**Pipeline:**
```
Query → MultiStrategyRouter → LLM → Direct Answer
```

**Примеры:**
- "Что такое шенгенская виза?"
- "Какая столица Франции?"
- "Сколько часов лететь до Парижа?"

### 2. REACT Strategy

**Использование:** Гибкие исследовательские задачи без четкого плана

**Pipeline:**
```
Query → MultiStrategyRouter → TravelReActAgent →
    ↓
[ReAct Loop]
    Thought: обдумывание
    Action: выбор инструмента
    Observation: результат
    (повтор до решения)
    ↓
Final Answer
```

**Примеры:**
- "Исследуй варианты отдыха в Юго-Восточной Азии"
- "Подбери что-нибудь интересное в Европе"
- "Посоветуй куда поехать весной"

### 3. PLAN_EXECUTE Strategy

**Использование:** Структурированные задачи с четкими шагами

**Pipeline:**
```
Query → MultiStrategyRouter →
    ↓
ContextExtractor → IntentClassifier →
    ↓
TaskPlanner (создает DAG план) →
    ↓
PlanOrchestrator (параллельное выполнение) →
    ↓
ResultReflector (проверка + replan если нужно) →
    ↓
Final Answer
```

**Примеры:**
- "Найди рейсы из Москвы в Париж на 20 января"
- "Какая погода в Берлине?"
- "Спланируй: погода + рейсы + отель в Токио"

---

## 🔧 Компоненты

### MultiStrategyRouter

**Функции:**
- Классификация запросов на 3 типа (SIMPLE/REACT/PLAN_EXECUTE)
- Двухуровневая стратегия: эвристика + LLM
- Паттерны ключевых слов для быстрой классификации
- LLM классификация при неопределенности

**Пример использования:**
```python
from core.router import MultiStrategyRouter
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(model="gpt-4o-mini")
router = MultiStrategyRouter(llm)

decision = await router.route("Найди рейсы в Париж")
print(decision.route_type)  # RouteType.PLAN_EXECUTE
```

### TravelReActAgent

**Функции:**
- ReAct loop (Reasoning + Acting)
- Гибкая адаптация на ходу
- Streaming поддержка
- Обработка ошибок

**Пример использования:**
```python
from agents.react_agent import TravelReActAgent

agent = TravelReActAgent(llm=llm, tools=tools)

async for event in agent.run(query, session_id):
    print(event)  # react_thought, react_action, react_observation
```

### TaskPlanner + PlanOrchestrator

**Функции:**
- Создание структурированных DAG планов
- Параллельное выполнение независимых шагов
- Обработка зависимостей между шагами
- Валидация циклических зависимостей

**Пример плана:**
```json
{
  "goal": "Найти рейсы Москва→Париж на 20 января",
  "steps": [
    {
      "id": 1,
      "action": "get_weather",
      "params": {"city": "Paris"},
      "depends_on": [],
      "can_parallel": true
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
      "can_parallel": true
    }
  ]
}
```

---

## 📡 API Endpoints

### `GET /api/stream`

SSE streaming endpoint для реального времени

**Query Parameters:**
- `q` (string, required) - запрос пользователя
- `session_id` (string, optional) - ID сессии для памяти

**SSE Events:**

**Common:**
- `start` - Agent started
- `routing_complete` - Routing decision (includes strategy)
- `done` - Processing complete

**SIMPLE:**
- `simple_answer` - Direct answer

**REACT:**
- `react_start` - ReAct started
- `react_thought` - Reasoning step
- `react_action` - Tool action
- `react_observation` - Tool result
- `react_complete` - ReAct finished

**PLAN_EXECUTE:**
- `planning_start/plan_created` - Plan creation
- `execution_start/execution_complete` - Execution
- `reflection_complete` - Result reflection
- `final_answer` - Final answer

---

## 🧪 Тестирование

```bash
# Запустить unit тесты
python -m pytest tests/

# Тестирование router
python core/router.py

# Тестирование ReAct agent
python agents/react_agent.py

# Тестирование моделей
python core/models.py
```

---

## 🚢 Деплой

### Render

1. Создайте Web Service на [Render](https://render.com)
2. Подключите Git репозиторий
3. Настройте:
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `uvicorn api.server:app --host 0.0.0.0 --port 10000`
4. Добавьте Environment Variables:
   - `OPENAI_API_KEY`
   - `MODEL_NAME` (optional)

---

## 📝 Changelog

### Version 3.0.0 - Multi-Strategy Router
- ✨ Добавлен Multi-Strategy Router с 3 стратегиями
- ✨ Добавлен TravelReActAgent для гибких задач
- ✨ Обновлен TravelAgent с поддержкой всех стратегий
- ✨ Обновлен API с новыми SSE событиями
- 📝 Обновлена документация

### Version 2.1 - Plan-and-Execute + Context Management
- ✨ План-and-Execute архитектура
- ✨ Context Management (StateManager, ContextExtractor)
- ✨ Параллельное выполнение задач
- ✨ Result Reflection + Replan логика

### Version 1.0 - MVP ReAct
- 🎉 Первая версия с ReAct паттерном
- ✨ Google ADK агент
- ✨ SSE Streaming

---

## 🛠️ Технологии

- **LangChain** - Фреймворк для LLM приложений
- **OpenAI GPT-4o-mini** - Language model
- **FastAPI** - Modern web framework
- **SSE (Server-Sent Events)** - Real-time streaming
- **Pydantic** - Data validation
- **AsyncIO** - Асинхронное выполнение

---

## 📄 Лицензия

MIT License

---

## 🤝 Contributing

Pull requests are welcome! For major changes, please open an issue first.

---

## 📧 Контакты

Вопросы? Создайте Issue на GitHub!
