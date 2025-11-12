/**
 * Travel Agent V2 - Plan-and-Execute Premium Interface
 * Clean, minimal, production-ready
 * Version: 2.3.0 - Final
 * 
 * Изменения:
 * - Удален typing indicator (избыточен)
 * - План интегрирован внутрь Thinking Block
 * - Весь интерфейс на русском языке
 * - Thinking Block свернут по умолчанию
 */

// ============================================================================
// GLOBAL STATE
// ============================================================================
let currentEventSource = null;
let sessionId = null;
let currentThinkingBlock = null;
let currentAssistantMessage = null;
let currentPlanSection = null;

// ============================================================================
// INITIALIZATION
// ============================================================================
document.addEventListener('DOMContentLoaded', () => {
    console.log('Travel Agent V2 Premium UI initialized (Plan-and-Execute)');

    // Initialize session
    sessionId = getSessionId();

    // Setup input handlers
    setupInputHandlers();

    // Auto-resize textarea
    autoResizeTextarea();
});

// ============================================================================
// SESSION MANAGEMENT
// ============================================================================
function getSessionId() {
    let id = sessionStorage.getItem('travel_agent_session_id');
    if (!id) {
        id = `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
        sessionStorage.setItem('travel_agent_session_id', id);
    }
    return id;
}

// ============================================================================
// INPUT HANDLERS
// ============================================================================
function setupInputHandlers() {
    const input = document.getElementById('messageInput');
    const sendBtn = document.getElementById('sendBtn');

    // Enable/disable send button based on input
    input.addEventListener('input', () => {
        const hasText = input.value.trim().length > 0;
        sendBtn.disabled = !hasText;
    });

    // Keyboard shortcuts
    input.addEventListener('keydown', (e) => {
        // Enter = send (without Shift)
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            if (!sendBtn.disabled) {
                sendMessage();
            }
        }
    });
}

function autoResizeTextarea() {
    const input = document.getElementById('messageInput');

    input.addEventListener('input', function() {
        this.style.height = 'auto';
        this.style.height = Math.min(this.scrollHeight, 200) + 'px';
    });
}

// ============================================================================
// SEND MESSAGE
// ============================================================================
function sendMessage() {
    const input = document.getElementById('messageInput');
    const message = input.value.trim();

    if (!message) return;

    // Disable input
    setInputEnabled(false);

    // Add user message to chat
    addUserMessage(message);

    // Clear input
    input.value = '';
    input.style.height = 'auto';

    // Start streaming response
    startStreaming(message);
}

// ============================================================================
// MESSAGE COMPONENTS
// ============================================================================
function addUserMessage(text) {
    // Hide welcome screen on first message
    const welcomeScreen = document.getElementById('welcomeScreen');
    if (welcomeScreen && !welcomeScreen.classList.contains('hidden')) {
        welcomeScreen.classList.add('hidden');
    }

    const chatContainer = document.getElementById('chatContainer');

    const messageEl = document.createElement('div');
    messageEl.className = 'message user';
    messageEl.innerHTML = `
        <div class="message-avatar">Вы</div>
        <div class="message-content">
            <div class="message-text">${escapeHtml(text)}</div>
        </div>
    `;

    chatContainer.appendChild(messageEl);
    scrollToBottom();
}

function addAssistantMessage() {
    const chatContainer = document.getElementById('chatContainer');

    const messageEl = document.createElement('div');
    messageEl.className = 'message assistant';
    messageEl.innerHTML = `
        <div class="message-avatar">AI</div>
        <div class="message-content">
            <!-- Thinking block, plan, and answer will be added here -->
        </div>
    `;

    chatContainer.appendChild(messageEl);
    currentAssistantMessage = messageEl;
    scrollToBottom();

    return messageEl;
}

// ============================================================================
// THINKING BLOCK - Единый блок для всего процесса (план внутри)
// ============================================================================
function createThinkingBlock(title = 'Обработка') {
    if (!currentAssistantMessage) {
        addAssistantMessage();
    }

    const content = currentAssistantMessage.querySelector('.message-content');

    const thinkingEl = document.createElement('div');
    thinkingEl.className = 'thinking-block collapsed'; // Свернут по умолчанию

    thinkingEl.innerHTML = `
        <div class="thinking-header" onclick="toggleThinking(this)">
            <div class="thinking-title">
                <svg class="thinking-icon spinning" viewBox="0 0 24 24" fill="none">
                    <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2" opacity="0.25"/>
                    <path d="M12 2a10 10 0 0 1 10 10" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
                </svg>
                <span>${title}</span>
            </div>
            <span class="thinking-meta"></span>
            <svg class="thinking-chevron" viewBox="0 0 24 24" fill="none">
                <path d="M6 9l6 6 6-6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
        </div>
        <div class="thinking-content">
            <div class="thinking-steps"></div>
        </div>
    `;

    content.appendChild(thinkingEl);
    currentThinkingBlock = thinkingEl;
    scrollToBottom();

    return thinkingEl;
}

function addThinkingStep(type, content) {
    if (!currentThinkingBlock) {
        createThinkingBlock();
    }

    const stepsContainer = currentThinkingBlock.querySelector('.thinking-steps');

    const stepEl = document.createElement('div');
    stepEl.className = 'thinking-step';
    stepEl.innerHTML = `
        <div class="thinking-step-label">${getStepLabel(type)}</div>
        <div class="thinking-step-text">${escapeHtml(content)}</div>
    `;

    stepsContainer.appendChild(stepEl);
    scrollToBottom();
}

function finishThinking() {
    if (!currentThinkingBlock) return;

    const icon = currentThinkingBlock.querySelector('.thinking-icon');
    if (icon) {
        icon.classList.remove('spinning');
    }

    const title = currentThinkingBlock.querySelector('.thinking-title span');
    if (title) {
        title.textContent = 'Завершено';
    }
}

function toggleThinking(header) {
    const thinkingBlock = header.closest('.thinking-block');
    thinkingBlock.classList.toggle('collapsed');
}

function getStepLabel(stepType) {
    const labels = {
        'routing': '🔀 Маршрутизация:',
        'planning': '📋 Планирование:',
        'execution': '⚙️ Выполнение:',
        'reflection': '🔍 Анализ:',
        'replan': '🔄 Перепланирование:'
    };
    return labels[stepType] || 'Шаг:';
}

function updateThinkingMeta(stepCount) {
    if (!currentThinkingBlock) return;
    
    const meta = currentThinkingBlock.querySelector('.thinking-meta');
    if (meta) {
        let label = 'шагов';
        if (stepCount === 1) {
            label = 'шаг';
        } else if (stepCount > 1 && stepCount < 5) {
            label = 'шага';
        }
        meta.textContent = `${stepCount} ${label}`;
    }
}

// ============================================================================
// PLAN SECTION - Внутри Thinking Block
// ============================================================================
function createPlanSection(planData) {
    if (!currentThinkingBlock) return;

    const thinkingContent = currentThinkingBlock.querySelector('.thinking-content');

    const planEl = document.createElement('div');
    planEl.className = 'plan-section';

    const stepsList = planData.steps.map((step) => {
        const parallelIcon = step.can_parallel ? '⚡' : '➡️';
        const depsText = step.depends_on && step.depends_on.length > 0 
            ? ` (зависит от: ${step.depends_on.join(', ')})` 
            : '';

        return `
            <div class="plan-step" data-step-id="${step.id}">
                <div class="plan-step-header">
                    <span class="plan-step-icon">${parallelIcon}</span>
                    <span class="plan-step-number">${step.id}.</span>
                    <span class="plan-step-description">${escapeHtml(step.description)}</span>
                </div>
                <div class="plan-step-meta">
                    <span class="plan-step-action">${escapeHtml(step.action)}</span>
                    <span class="plan-step-time">~${step.estimated_time} сек</span>
                    ${depsText ? `<span class="plan-step-deps">${depsText}</span>` : ''}
                </div>
                <div class="plan-step-status">⏳ Ожидает</div>
            </div>
        `;
    }).join('');

    planEl.innerHTML = `
        <div class="plan-section-title">
            <svg viewBox="0 0 24 24" fill="none">
                <path d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" stroke="currentColor" stroke-width="2"/>
                <path d="M9 12l2 2 4-4" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
            </svg>
            <span>${escapeHtml(planData.goal)}</span>
            <span class="plan-section-meta">~${planData.total_estimated_time} сек</span>
        </div>
        <div class="plan-steps">${stepsList}</div>
    `;

    thinkingContent.appendChild(planEl);
    currentPlanSection = planEl;
    scrollToBottom();

    // Обновить meta в thinking header
    updateThinkingMeta(planData.steps.length);

    return planEl;
}

function updateStepStatus(stepId, status, data = null) {
    // Ищем plan-section внутри currentThinkingBlock
    if (!currentThinkingBlock) return;

    const planSection = currentThinkingBlock.querySelector('.plan-section');
    if (!planSection) return;

    const stepEl = planSection.querySelector(`.plan-step[data-step-id="${stepId}"]`);
    if (!stepEl) return;

    const statusEl = stepEl.querySelector('.plan-step-status');

    if (status === 'running') {
        statusEl.innerHTML = '▶️ Выполняется...';
        statusEl.className = 'plan-step-status running';
        stepEl.classList.add('active');
    } else if (status === 'completed') {
        const time = data?.execution_time ? ` (${data.execution_time.toFixed(1)} сек)` : '';
        statusEl.innerHTML = `✅ Завершено${time}`;
        statusEl.className = 'plan-step-status completed';
        stepEl.classList.remove('active');
        stepEl.classList.add('completed');
    } else if (status === 'failed') {
        const error = data?.error ? `: ${data.error.substring(0, 50)}...` : '';
        statusEl.innerHTML = `❌ Не удалось${error}`;
        statusEl.className = 'plan-step-status failed';
        stepEl.classList.remove('active');
        stepEl.classList.add('failed');
    }

    scrollToBottom();
}

// ============================================================================
// REACT SECTION - Внутри Thinking Block (NEW)
// ============================================================================
let currentReActSection = null;
let reactStepCounter = 0;

function createReActSection() {
    if (!currentThinkingBlock) return;

    const thinkingContent = currentThinkingBlock.querySelector('.thinking-content');

    const reactEl = document.createElement('div');
    reactEl.className = 'react-section';
    reactEl.innerHTML = `
        <div class="react-section-title">
            <svg viewBox="0 0 24 24" fill="none">
                <circle cx="12" cy="12" r="3" stroke="currentColor" stroke-width="2"/>
                <path d="M12 2v4M12 18v4M2 12h4M18 12h4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
            </svg>
            <span>ReAct Loop: Reasoning + Acting</span>
        </div>
        <div class="react-steps"></div>
    `;

    thinkingContent.appendChild(reactEl);
    currentReActSection = reactEl;
    reactStepCounter = 0;
    scrollToBottom();

    return reactEl;
}

function addReActThought(stepNum, thought) {
    if (!currentReActSection) {
        createReActSection();
    }

    const stepsContainer = currentReActSection.querySelector('.react-steps');

    // Создаем или находим контейнер для текущего шага
    let stepContainer = stepsContainer.querySelector(`.react-step-container[data-step="${stepNum}"]`);
    if (!stepContainer) {
        stepContainer = document.createElement('div');
        stepContainer.className = 'react-step-container';
        stepContainer.setAttribute('data-step', stepNum);
        stepContainer.innerHTML = `
            <div class="react-step-number">Шаг ${stepNum}</div>
        `;
        stepsContainer.appendChild(stepContainer);
        reactStepCounter++;
        updateThinkingMeta(reactStepCounter);
    }

    const thoughtEl = document.createElement('div');
    thoughtEl.className = 'react-thought';
    thoughtEl.innerHTML = `
        <div class="react-step-icon">💭</div>
        <div class="react-step-content">
            <div class="react-step-label">Thought:</div>
            <div class="react-step-text">${escapeHtml(thought)}</div>
        </div>
    `;

    stepContainer.appendChild(thoughtEl);
    scrollToBottom();
}

function addReActAction(stepNum, tool, toolInput) {
    if (!currentReActSection) return;

    const stepsContainer = currentReActSection.querySelector('.react-steps');
    let stepContainer = stepsContainer.querySelector(`.react-step-container[data-step="${stepNum}"]`);
    if (!stepContainer) return;

    const actionEl = document.createElement('div');
    actionEl.className = 'react-action';

    let inputDisplay = '';
    if (typeof toolInput === 'object') {
        inputDisplay = JSON.stringify(toolInput, null, 2);
    } else {
        inputDisplay = toolInput;
    }

    actionEl.innerHTML = `
        <div class="react-step-icon">🔧</div>
        <div class="react-step-content">
            <div class="react-step-label">Action:</div>
            <div class="react-step-text">
                <strong>${escapeHtml(tool)}</strong>
                <pre class="react-code">${escapeHtml(inputDisplay)}</pre>
            </div>
        </div>
    `;

    stepContainer.appendChild(actionEl);
    scrollToBottom();
}

function addReActObservation(stepNum, result) {
    if (!currentReActSection) return;

    const stepsContainer = currentReActSection.querySelector('.react-steps');
    let stepContainer = stepsContainer.querySelector(`.react-step-container[data-step="${stepNum}"]`);
    if (!stepContainer) return;

    const observationEl = document.createElement('div');
    observationEl.className = 'react-observation';

    let resultDisplay = '';
    if (typeof result === 'object') {
        resultDisplay = JSON.stringify(result, null, 2);
    } else {
        resultDisplay = String(result);
    }

    observationEl.innerHTML = `
        <div class="react-step-icon">👀</div>
        <div class="react-step-content">
            <div class="react-step-label">Observation:</div>
            <div class="react-step-text">
                <pre class="react-result">${escapeHtml(resultDisplay)}</pre>
            </div>
        </div>
    `;

    stepContainer.appendChild(observationEl);
    scrollToBottom();
}

// ============================================================================
// FINAL ANSWER
// ============================================================================
function addFinalAnswer(text) {
    if (!currentAssistantMessage) {
        addAssistantMessage();
    }

    const content = currentAssistantMessage.querySelector('.message-content');

    const answerEl = document.createElement('div');
    answerEl.className = 'message-text';
    answerEl.textContent = text;

    content.appendChild(answerEl);
    scrollToBottom();

    // Finish thinking block
    if (currentThinkingBlock) {
        finishThinking();
    }
}

// ============================================================================
// SSE STREAMING (Plan-and-Execute V2)
// ============================================================================
function startStreaming(query) {
    // Close existing connection
    if (currentEventSource) {
        currentEventSource.close();
    }

    // Reset state
    currentThinkingBlock = null;
    currentAssistantMessage = null;
    currentPlanSection = null;

    // Create URL
    const url = `/api/stream?q=${encodeURIComponent(query)}&session_id=${encodeURIComponent(sessionId)}`;

    try {
        currentEventSource = new EventSource(url);
        setupSSEListeners(currentEventSource);
    } catch (error) {
        console.error('Error creating EventSource:', error);
        addErrorMessage('Не удалось подключиться к серверу');
        setInputEnabled(true);
    }
}

function setupSSEListeners(eventSource) {
    // Start event
    eventSource.addEventListener('start', (event) => {
        console.log('Agent started (Plan-and-Execute)');
        // Не добавляем typing indicator - он удален
    });

    // Routing events
    eventSource.addEventListener('routing_start', (event) => {
        createThinkingBlock('Обработка');
        addThinkingStep('routing', 'Анализирую тип запроса...');
    });

    eventSource.addEventListener('routing_complete', (event) => {
        const data = JSON.parse(event.data);
        const confidence = (data.confidence * 100).toFixed(0);
        const strategyLabels = {
            'simple': 'Simple (прямой ответ)',
            'react': 'ReAct (исследование)',
            'plan_execute': 'Plan-Execute (планирование)'
        };
        const strategyLabel = strategyLabels[data.strategy] || data.route_type;
        addThinkingStep('routing', `Стратегия: ${strategyLabel} (уверенность: ${confidence}%)`);
    });

    // Strategy info event (NEW)
    eventSource.addEventListener('strategy', (event) => {
        const data = JSON.parse(event.data);
        addThinkingStep('routing', `Использую стратегию: ${data.name}`);
    });

    // Simple answer (no agent needed)
    eventSource.addEventListener('simple_answer', (event) => {
        const data = JSON.parse(event.data);
        addFinalAnswer(data.answer);

        eventSource.close();
        currentEventSource = null;
        setInputEnabled(true);
    });

    // ========================================================================
    // REACT STRATEGY EVENTS (NEW)
    // ========================================================================

    eventSource.addEventListener('react_start', (event) => {
        const data = JSON.parse(event.data);
        createReActSection();
        addThinkingStep('execution', `ReAct Agent запущен (макс. ${data.max_iterations || 15} итераций)`);
    });

    eventSource.addEventListener('react_thought', (event) => {
        const data = JSON.parse(event.data);
        addReActThought(data.step || 1, data.thought);
    });

    eventSource.addEventListener('react_action', (event) => {
        const data = JSON.parse(event.data);
        addReActAction(data.step || 1, data.tool, data.tool_input);
    });

    eventSource.addEventListener('react_observation', (event) => {
        const data = JSON.parse(event.data);
        addReActObservation(data.step || 1, data.result);
    });

    eventSource.addEventListener('react_complete', (event) => {
        const data = JSON.parse(event.data);
        addThinkingStep('reflection', `ReAct завершен за ${data.total_steps || 0} шагов`);
        if (data.answer) {
            addFinalAnswer(data.answer);
        }
    });

    eventSource.addEventListener('react_error', (event) => {
        const data = JSON.parse(event.data);
        addThinkingStep('error', `Ошибка ReAct: ${data.error}`);
    });

    // Planning events
    eventSource.addEventListener('planning_start', (event) => {
        addThinkingStep('planning', 'Анализирую задачу и создаю план выполнения...');
    });

    eventSource.addEventListener('plan_created', (event) => {
        const data = JSON.parse(event.data);
        createPlanSection(data);
    });

    // Execution events
    eventSource.addEventListener('execution_start', (event) => {
        console.log('Plan execution started');
    });

    eventSource.addEventListener('step_started', (event) => {
        const data = JSON.parse(event.data);
        if (data.step_id) {
            updateStepStatus(data.step_id, 'running');
        }
    });

    eventSource.addEventListener('step_completed', (event) => {
        const data = JSON.parse(event.data);
        if (data.step_id) {
            updateStepStatus(data.step_id, 'completed', data);
        }
    });

    eventSource.addEventListener('step_failed', (event) => {
        const data = JSON.parse(event.data);
        if (data.step_id) {
            updateStepStatus(data.step_id, 'failed', data);
        }
    });

    // Reflection events
    eventSource.addEventListener('reflection_start', (event) => {
        console.log('Reflection started');
        addThinkingStep('reflection', 'Анализирую результаты выполнения...');
    });

    eventSource.addEventListener('reflection_complete', (event) => {
        const data = JSON.parse(event.data);
        console.log('Reflection:', data.status);
        if (data.status === 'success') {
            addThinkingStep('reflection', 'Все задачи выполнены успешно');
        } else if (data.status === 'needs_replan') {
            addThinkingStep('reflection', 'Требуется перепланирование');
        }
    });

    // Replan event
    eventSource.addEventListener('replan', (event) => {
        const data = JSON.parse(event.data);
        addThinkingStep('replan', data.reason || 'Создаю новый план...');
    });

    // Needs user input
    eventSource.addEventListener('needs_user_input', (event) => {
        const data = JSON.parse(event.data);
        const questions = data.questions.join('\n• ');
        addFinalAnswer(`Мне нужна дополнительная информация:\n\n• ${questions}`);

        eventSource.close();
        currentEventSource = null;
        setInputEnabled(true);
    });

    // Final answer
    eventSource.addEventListener('final_answer', (event) => {
        const data = JSON.parse(event.data);
        addFinalAnswer(data.answer);
    });

    // Done event
    eventSource.addEventListener('done', (event) => {
        console.log('Processing complete');

        // Финализировать thinking block
        if (currentThinkingBlock) {
            finishThinking();
        }

        // Cleanup
        eventSource.close();
        currentEventSource = null;
        setInputEnabled(true);
    });

    // Error event
    eventSource.addEventListener('error', (event) => {
        console.error('SSE Error:', event);

        if (event.data) {
            try {
                const data = JSON.parse(event.data);
                addErrorMessage(data.error || 'Произошла ошибка');
            } catch (e) {
                addErrorMessage('Произошла ошибка');
            }
        } else {
            if (eventSource.readyState === EventSource.CLOSED) {
                console.log('SSE connection closed');
            } else {
                addErrorMessage('Потеряно соединение с сервером');
            }
        }

        // Cleanup
        eventSource.close();
        currentEventSource = null;
        setInputEnabled(true);
    });
}

// ============================================================================
// ERROR HANDLING
// ============================================================================
function addErrorMessage(text) {
    if (!currentAssistantMessage) {
        addAssistantMessage();
    }

    const content = currentAssistantMessage.querySelector('.message-content');

    const errorEl = document.createElement('div');
    errorEl.className = 'message-text';
    errorEl.style.color = '#ef4444';
    errorEl.textContent = `Ошибка: ${text}`;

    content.appendChild(errorEl);
    scrollToBottom();

    // Finish thinking block if exists
    if (currentThinkingBlock) {
        finishThinking();
    }
}

// ============================================================================
// UI UTILITIES
// ============================================================================
function setInputEnabled(enabled) {
    const input = document.getElementById('messageInput');
    const sendBtn = document.getElementById('sendBtn');

    input.disabled = !enabled;

    if (enabled) {
        input.focus();
        sendBtn.disabled = input.value.trim().length === 0;
    } else {
        sendBtn.disabled = true;
    }
}

function scrollToBottom() {
    const chatContainer = document.getElementById('chatContainer');
    chatContainer.scrollTop = chatContainer.scrollHeight;
}

function escapeHtml(text) {
    if (typeof text !== 'string') {
        text = String(text);
    }
    
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
