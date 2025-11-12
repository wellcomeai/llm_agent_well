# 🔍 Debug Guide - SSE Streaming Issues

## Проблема

Финальные ответы генерируются на сервере, но не доходят до UI. События SSE теряются между сервером и клиентом.

## Внесенные исправления

### 1. ✅ Server-side Logging (api/server.py)

Добавлено детальное логирование для каждого SSE события:

```python
print(f"📤 [SSE] Sending START event to client (session: {session_id})")
print(f"📤 [SSE] Sending {event_type.upper()} event: {content_preview}...")
print(f"⚠️  [SSE] Client disconnected for session {session_id}")
print(f"❌ [SSE] Error in event_generator: {error_msg}")
print(f"🏁 [SSE] Event generator finished for session {session_id}")
```

**Что проверять в логах сервера:**
- Все события отправляются (START, ACT, OBSERVE, DONE)
- DONE событие содержит контент (не пустое)
- Нет сообщений о disconnection до отправки DONE
- Нет exceptions в event_generator

### 2. ✅ Agent-side Logging (agents/travel_agent.py)

Добавлено логирование перед каждым yield:

```python
logger.info(f"📤 Yielding START event: {start_event['content']}")
logger.info(f"📤 Yielding ACT event: {function_name} with args {function_args}")
logger.info(f"📤 Yielding OBSERVE event: success={function_result.get('success', False)}")
logger.info(f"📤 Yielding DONE event with content length: {len(done_event['content'])}")
logger.info(f"📤 DONE content preview: {done_event['content'][:100]}...")
```

**Что проверять в логах агента:**
- Все yield выполняются
- DONE event содержит контент
- Контент не None и не пустая строка

### 3. ✅ Session History Limit (agents/travel_agent.py)

Добавлено ограничение размера истории для предотвращения переполнения контекста:

```python
self.max_history_messages = 20  # Лимит сообщений в истории

# Автоматическое обрезание истории
if len(self.sessions[session_id]) > self.max_history_messages:
    logger.warning(f"Session history exceeds {self.max_history_messages} messages, trimming...")
    system_msg = self.sessions[session_id][0]
    recent_messages = self.sessions[session_id][-(self.max_history_messages - 1):]
    self.sessions[session_id] = [system_msg] + recent_messages
```

**Зачем:**
- Предотвращает переполнение контекста OpenAI API
- Уменьшает стоимость запросов
- Ускоряет обработку

### 4. ✅ Client-side Logging (frontend/static/app.js)

Добавлено детальное логирование всех SSE событий:

```javascript
eventSource.onopen = () => {
    console.log('✅ [SSE] Connection opened');
};

console.log('📥 [SSE] Received START event:', event.data);
console.log('📥 [SSE] Received ACT event:', event.data);
console.log('📥 [SSE] Received OBSERVE event:', event.data);
console.log('📥 [SSE] Received DONE event:', event.data);
console.log('📥 [SSE] DONE content length:', step.content?.length || 0);
console.log('📥 [SSE] DONE content preview:', step.content?.substring(0, 100));

console.error('❌ [SSE] Error event:', event);
console.error('❌ [SSE] ReadyState:', eventSource.readyState);
```

**Что проверять в Browser Console:**
- Connection opened успешно
- Все события приходят (START, ACT, OBSERVE, DONE)
- DONE содержит контент (length > 0)
- Нет ошибок SSE
- ReadyState = 1 (OPEN) во время работы

### 5. ✅ UI Rendering Debug (frontend/static/app.js)

Добавлено логирование в функции отображения:

```javascript
console.log('💬 [UI] showFinalResponse called with text length:', text?.length || 0);
console.log('💬 [UI] Text preview:', text?.substring(0, 100));
console.log('💬 [UI] Found assistantText element, setting content');
console.log('💬 [UI] Content displayed successfully');
```

**Что проверять:**
- showFinalResponse вызывается
- Text length > 0
- assistantText element найден
- Content displayed успешно

### 6. ✅ SSE Delay Увеличен

Увеличена задержка между событиями с 0.1s до 0.2s:

```python
await asyncio.sleep(0.2)  # Было 0.1
```

**Зачем:**
- Предотвращает переполнение буфера на клиенте
- Дает больше времени на обработку каждого события
- Помогает с большими событиями (DONE с длинным контентом)

## Как тестировать

### Шаг 1: Запустить сервер с логами

```bash
cd /home/user/llm_agent_well
python api/server.py
```

### Шаг 2: Открыть Browser DevTools

- Chrome/Firefox: F12
- Вкладка **Console**
- Фильтр: оставить только "[SSE]" и "[UI]"

### Шаг 3: Отправить тестовый запрос

Примеры:
- "Какая погода в Париже?"
- "Найди рейсы из Амстердама в Лондон"

### Шаг 4: Проверить логи

#### В Server Console должно быть:

```
📤 [SSE] Sending START event to client (session: session_xyz)
📤 Yielding START event: Обрабатываю запрос...
📤 Yielding ACT event: get_weather with args {'city': 'Paris'}
📤 [SSE] Sending ACT event: Вызываю функцию: get_weather...
📤 Yielding OBSERVE event: success=True
📤 [SSE] Sending OBSERVE event: Результат функции get_weather...
📤 Yielding DONE event with content length: 1564
📤 DONE content preview: В Париже сейчас +15°C, облачно...
📤 [SSE] Sending DONE event: В Париже сейчас +15°C...
✅ Agent completed successfully
🏁 [SSE] Event generator finished for session session_xyz
```

#### В Browser Console должно быть:

```
✅ [SSE] Connection opened
📥 [SSE] Received START event: {...}
📥 [SSE] Received ACT event: {...}
📥 [SSE] Received OBSERVE event: {...}
📥 [SSE] Received DONE event: {"step_type":"done","content":"В Париже сейчас +15°C...","timestamp":"..."}
📥 [SSE] DONE content length: 1564
📥 [SSE] DONE content preview: В Париже сейчас +15°C, облачно...
💬 [UI] showFinalResponse called with text length: 1564
💬 [UI] Text preview: В Париже сейчас +15°C, облачно...
💬 [UI] Found assistantText element, setting content
💬 [UI] Content displayed successfully
✅ [SSE] Closing connection
```

### Шаг 5: Проверить UI

- Должно появиться сообщение ассистента
- Thinking section должен быть свернут
- Финальный ответ должен быть виден
- Время выполнения должно отобразиться

## Возможные проблемы и решения

### Проблема 1: DONE событие не приходит на клиент

**Признаки:**
- В server logs: "Sending DONE event"
- В browser console: нет "Received DONE event"

**Решения:**
1. Проверить Network tab -> EventSource соединение
2. Проверить, нет ли ошибок CORS
3. Попробовать увеличить задержку до 0.5s
4. Проверить, не обрывается ли соединение по таймауту

### Проблема 2: DONE приходит, но контент пустой

**Признаки:**
- "Received DONE event" есть
- "DONE content length: 0"

**Решения:**
1. Проверить agent logs - есть ли контент в yield
2. Проверить, что message.content не None
3. Проверить, что JSON.dumps не ломает контент

### Проблема 3: Контент есть, но не отображается

**Признаки:**
- "DONE content length: 1564"
- "showFinalResponse called"
- Но на экране ничего нет

**Решения:**
1. Проверить, что assistantText element найден
2. Проверить CSS - может быть display: none
3. Проверить, что нет других JS ошибок
4. Проверить, что removeAttribute('id') не удаляет нужный элемент

### Проблема 4: Session history переполняется

**Признаки:**
- OpenAI API error: "context length exceeded"
- Медленные ответы после нескольких запросов

**Решения:**
1. История автоматически обрезается до 20 сообщений
2. Можно уменьшить лимит: `self.max_history_messages = 10`
3. Или очищать историю вручную через clearChat()

## Production Checklist

Перед деплоем на Render проверить:

- [ ] Все логи работают локально
- [ ] DONE события доходят до UI
- [ ] Финальные ответы отображаются
- [ ] Session history не переполняется
- [ ] Network tab показывает успешные EventSource соединения
- [ ] Нет ошибок в console
- [ ] Таймауты достаточные (Render может обрывать через 30s)
- [ ] OPENAI_API_KEY установлен в Render environment

## Дополнительные улучшения (опционально)

### 1. Таймаут для SSE

```javascript
const timeout = setTimeout(() => {
    console.error('⏰ [SSE] Timeout after 60s');
    eventSource.close();
    showError('Таймаут: ответ не получен в течение 60 секунд');
}, 60000);

// В done event:
clearTimeout(timeout);
```

### 2. Retry логика

```javascript
let retryCount = 0;
const maxRetries = 3;

eventSource.onerror = (error) => {
    if (retryCount < maxRetries) {
        retryCount++;
        console.log(`🔄 [SSE] Retry ${retryCount}/${maxRetries}`);
        setTimeout(() => sendMessage(), 2000);
    } else {
        console.error('❌ [SSE] Max retries reached');
    }
};
```

### 3. Heartbeat проверка

```python
# В server.py
async def event_generator():
    last_heartbeat = time.time()

    async for step in agent_instance.run(q, session_id):
        # ... отправка события

        # Каждые 10 секунд отправляем heartbeat
        if time.time() - last_heartbeat > 10:
            yield {
                "event": "heartbeat",
                "data": json.dumps({"status": "alive"})
            }
            last_heartbeat = time.time()
```

---

**Дата создания:** 2025-01-12
**Версия:** 1.0
**Статус:** Все исправления внедрены ✅
