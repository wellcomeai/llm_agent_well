# 🧳 Travel Agent MVP

MVP агента-помощника путешествий с **ReAct паттерном** на базе **LangChain**.

![Travel Agent Demo](https://img.shields.io/badge/status-MVP-blue)
![Python](https://img.shields.io/badge/python-3.11+-green)
![License](https://img.shields.io/badge/license-MIT-blue)

## 🎯 Возможности

- ✅ **Естественный языковой интерфейс** - общайтесь с агентом на русском языке
- ✅ **ReAct Loop** (Think → Act → Observe) - прозрачный процесс рассуждений
- ✅ **Real-time SSE Streaming** - наблюдайте за работой агента в реальном времени
- ✅ **Инструменты**: получение погоды и поиск рейсов
- ✅ **Память в рамках сессии** - контекст сохраняется во время диалога
- ✅ **LangChain Framework** - профессиональный фреймворк для LLM агентов
- ✅ **Smart Memory** - ConversationSummaryBufferMemory для длинных диалогов
- ✅ **Готов к деплою** на Render (или другие платформы)

## 🏗️ Архитектура

```
User Query
    ↓
[FastAPI + SSE]
    ↓
[TravelAgent (LangChain)]
    ↓
[ReAct Loop] ←→ [Functions: weather, flights]
    ↓
[SSE Stream] → Frontend (real-time reasoning)
```

### Компоненты

1. **Functions** (`functions/`) - Инструменты агента
   - `weather.py` - Получение погоды через wttr.in API
   - `flights.py` - Поиск рейсов (MVP: mock данные)

2. **Agents** (`agents/`) - Агенты с ReAct паттерном
   - `travel_agent.py` - Главный агент на LangChain

3. **API** (`api/`) - Backend сервер
   - `server.py` - FastAPI с SSE streaming

4. **Frontend** (`frontend/`) - Web интерфейс
   - `index.html` - Главная страница
   - `static/style.css` - Стили
   - `static/app.js` - SSE client логика

## 🚀 Быстрый старт

### Требования

- Python 3.11+
- OpenAI API Key

### Установка

```bash
# 1. Клонируй репозиторий
git clone https://github.com/YOUR_USERNAME/llm_agent_well.git
cd llm_agent_well

# 2. Создай виртуальное окружение
python -m venv venv

# Активируй виртуальное окружение
# Linux/Mac:
source venv/bin/activate
# Windows:
# venv\Scripts\activate

# 3. Установи зависимости
pip install -r requirements.txt

# 4. Настрой .env файл
cp .env.example .env
# Отредактируй .env - добавь свой OPENAI_API_KEY
```

### Настройка .env

Создай `.env` файл в корне проекта:

```bash
# OpenAI Configuration
OPENAI_API_KEY=sk-proj-your-key-here

# Model Settings
MODEL_NAME=gpt-4o-mini
TEMPERATURE=0.7
MAX_TOKENS=2000

# Server Configuration
HOST=0.0.0.0
PORT=8000

# Debug Mode
DEBUG=true
```

**Как получить OpenAI API Key:**

1. Перейди на [OpenAI Platform](https://platform.openai.com/api-keys)
2. Создай новый API ключ
3. Скопируй ключ в `.env` файл

### Запуск

```bash
# Из корня проекта
uvicorn api.server:app --reload --port 8000

# Или напрямую через Python
python api/server.py
```

После запуска открой браузер:
```
http://localhost:8000
```

## 📝 Примеры использования

### Пример 1: Запрос погоды

**Input:**
```
Какая погода в Париже?
```

**Reasoning Steps (в реальном времени):**
```
🚀 START: Агент начал работу
🤔 THINK: Нужно получить информацию о погоде в Париже
🔧 ACT: Вызываю get_weather("Paris")
👀 OBSERVE: Погода получена: +15°C, облачно, влажность 65%
✅ DONE: В Париже сейчас +15°C, облачно. Влажность 65%, ветер 12 км/ч.
         Отличная погода для прогулок!
```

### Пример 2: Планирование поездки

**Input:**
```
Спланируй поездку в Париж на выходные
```

**Reasoning Steps:**
```
🚀 START: Обрабатываю запрос
🤔 THINK: План действий:
         1. Узнать погоду в Париже
         2. Уточнить откуда пользователь летит
         3. Найти рейсы
🔧 ACT: Вызываю get_weather("Paris")
👀 OBSERVE: Погода: +15°C, облачно
✅ DONE: В Париже отличная погода (+15°C)!
         Из какого города вы планируете вылет, чтобы я мог найти рейсы?
```

### Пример 3: Полный запрос с рейсами

**Input:**
```
Хочу лететь из Амстердама в Париж завтра
```

**Reasoning Steps:**
```
🚀 START: Обрабатываю запрос
🤔 THINK: Нужна погода в Париже и рейсы из Амстердама
🔧 ACT: get_weather("Paris")
👀 OBSERVE: Температура +15°C, облачно
🔧 ACT: search_flights("Amsterdam", "Paris", "2025-01-16")
👀 OBSERVE: Найдено 3 рейса: KLM (89€), Air France (95€), EasyJet (65€)
✅ DONE: [Детальный план поездки с погодой и рейсами]
```

## 🧪 Тестирование

### Health Check

```bash
curl http://localhost:8000/health
```

**Response:**
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "agent_status": "healthy",
  "environment": {
    "google_api_key_set": true,
    "model_name": "gemini-2.0-flash-exp"
  }
}
```

### Non-streaming Query (для тестирования)

```bash
curl -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{"query": "Какая погода в Лондоне?"}'
```

### SSE Stream (в браузере)

```
http://localhost:8000/api/stream?q=погода%20в%20Токио
```

### Unit тесты

```bash
# Тестирование функций
python functions/weather.py
python functions/flights.py

# Тестирование агента
python agents/travel_agent.py
```

## 🎨 Frontend Features

- **Modern UI** - Минималистичный дизайн с градиентами
- **Real-time Streaming** - SSE для live обновлений
- **Step Visualization** - Разные цвета для каждого типа шага:
  - 🚀 START (синий) - Начало работы
  - 🤔 THINK (фиолетовый) - Размышление
  - 🔧 ACT (оранжевый) - Действие
  - 👀 OBSERVE (пурпурный) - Наблюдение
  - ✅ DONE (зеленый) - Завершение
  - ❌ ERROR (красный) - Ошибка
- **Keyboard Shortcuts**:
  - Enter - отправить запрос
  - Shift+Enter - новая строка
- **Session Memory** - Контекст сохраняется между запросами
- **Responsive Design** - Адаптация под мобильные устройства

## 🔧 Технологии

### Backend
- **Python 3.11** - Основной язык
- **LangChain** - Orchestration framework для агентов
- **FastAPI** - Современный async web framework
- **SSE (Server-Sent Events)** - Real-time streaming
- **Pydantic** - Валидация данных
- **python-dotenv** - Управление переменными окружения

### AI/ML
- **LangChain 0.1+** - Framework для LLM applications
- **OpenAI GPT-4o-mini** - LLM для агента
- **ReAct Pattern** - Reasoning and Acting paradigm
- **ConversationSummaryBufferMemory** - Smart memory management

### Frontend
- **Vanilla JavaScript** - Без фреймворков для простоты
- **EventSource API** - SSE client
- **CSS3** - Современные стили с градиентами и анимациями

### APIs
- **wttr.in** - Бесплатный API погоды
- **Mock Data** - Для поиска рейсов (MVP)

## 📦 Структура проекта

```
llm_agent_well/
│
├── functions/              # Инструменты агента
│   ├── __init__.py
│   ├── weather.py         # wttr.in API integration
│   └── flights.py         # Поиск рейсов (mock)
│
├── agents/                 # Агенты
│   ├── __init__.py
│   └── travel_agent.py    # Travel Agent с LangChain
│
├── api/                    # FastAPI backend
│   ├── __init__.py
│   └── server.py          # Endpoints + SSE streaming
│
├── frontend/               # Web интерфейс
│   ├── index.html
│   └── static/
│       ├── style.css      # Стили
│       └── app.js         # SSE client
│
├── tests/                  # Тесты (будущее)
│   └── test_agent.py
│
├── requirements.txt        # Python dependencies
├── runtime.txt            # Python версия
├── .env.example           # Пример env переменных
├── .gitignore
└── README.md
```

## 🚀 Деплой на Render

Проект готов к деплою на [Render](https://render.com):

### Шаги для деплоя:

1. **Push код на GitHub** (если еще не сделано)
   ```bash
   git add .
   git commit -m "Ready for deploy"
   git push origin main
   ```

2. **Создай Web Service на Render**
   - Перейди на [render.com](https://render.com)
   - New → Web Service
   - Подключи свой GitHub репозиторий

3. **Настрой Build & Start**
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn api.server:app --host 0.0.0.0 --port $PORT`

4. **Добавь Environment Variables**
   - `GOOGLE_API_KEY` = ваш API ключ
   - `MODEL_NAME` = gemini-2.0-flash-exp
   - `TEMPERATURE` = 0.7
   - `MAX_TOKENS` = 2000

5. **Deploy!**
   - Render автоматически задеплоит приложение
   - Получишь URL типа `https://your-app.onrender.com`

### Альтернативные платформы

Проект также совместим с:
- **Railway** - аналогично Render
- **Heroku** - требуется `Procfile`
- **Google Cloud Run** - требуется `Dockerfile`
- **AWS Lambda** - требуется адаптация для serverless

## 🔒 Безопасность

- ✅ API ключи хранятся в `.env` (не коммитятся в Git)
- ✅ CORS настроен (в production ограничить домены)
- ✅ Валидация входных данных через Pydantic
- ✅ Таймауты для внешних API запросов
- ✅ Обработка ошибок и исключений

**⚠️ Для production:**
- Добавь rate limiting
- Включи HTTPS
- Ограничь CORS конкретными доменами
- Добавь аутентификацию пользователей
- Используй secrets manager для API ключей

## 🛠️ Разработка

### Добавление новых инструментов

1. Создай файл в `functions/`:
```python
def my_new_tool(param: str) -> Dict[str, Any]:
    """
    Описание инструмента.
    """
    # Твоя логика
    return {"success": True, "data": "..."}

# Metadata для ADK
my_new_tool.metadata = {
    "name": "my_new_tool",
    "description": "Что делает инструмент",
    "parameters": {
        "type": "object",
        "properties": {
            "param": {
                "type": "string",
                "description": "Описание параметра"
            }
        },
        "required": ["param"]
    }
}
```

2. Импортируй в `agents/travel_agent.py`:
```python
from functions.my_tool import my_new_tool
```

3. Добавь в список инструментов:
```python
self.tools = [
    Tool(function_declarations=[
        # ... existing tools ...
        {
            "name": "my_new_tool",
            "description": "...",
            "parameters": {...}
        }
    ])
]
```

4. Добавь обработку в `_execute_function()`:
```python
elif function_name == "my_new_tool":
    return my_new_tool(**arguments)
```

### Логирование

Для debugging добавь логирование:
```python
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

logger.info("Agent started")
logger.debug(f"Query: {query}")
```

## 📊 Roadmap

### ✅ MVP (Done)
- [x] ReAct паттерн с LangChain
- [x] SSE streaming
- [x] Weather function (wttr.in)
- [x] Flights function (mock)
- [x] Frontend UI
- [x] Готовность к деплою

### 🔄 Следующие шаги
- [ ] Интеграция с реальным API рейсов (Amadeus, Skyscanner)
- [ ] Добавить инструмент для поиска отелей
- [ ] Добавить достопримечательности (Google Places API)
- [ ] Персистентная память (database)
- [ ] Аутентификация пользователей
- [ ] История диалогов
- [ ] Экспорт плана поездки (PDF, Email)
- [ ] Мультиязычность
- [ ] Unit и integration тесты
- [ ] CI/CD pipeline

## 🤝 Contributing

Contributions welcome! Please:

1. Fork репозиторий
2. Создай feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit изменения (`git commit -m 'Add some AmazingFeature'`)
4. Push в branch (`git push origin feature/AmazingFeature`)
5. Открой Pull Request

## 📄 Лицензия

MIT License - см. [LICENSE](LICENSE) файл для деталей.

## 👨‍💻 Автор

Created with ❤️ using LangChain and OpenAI

## 🙏 Acknowledgments

- [LangChain](https://python.langchain.com/) - Framework for LLM applications
- [FastAPI](https://fastapi.tiangolo.com/) - Web framework
- [wttr.in](https://wttr.in) - Weather API
- [SSE Starlette](https://github.com/sysid/sse-starlette) - SSE support

---

**Вопросы?** Открой [issue](https://github.com/YOUR_USERNAME/llm_agent_well/issues)

**Хочешь улучшить?** Создай [pull request](https://github.com/YOUR_USERNAME/llm_agent_well/pulls)

**Понравилось?** Поставь ⭐ на GitHub!
