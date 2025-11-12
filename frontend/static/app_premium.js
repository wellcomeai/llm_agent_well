/**
 * Travel Agent V2 - Plan-and-Execute Premium Interface
 * Clean, minimal, world-class UX
 */

// ============================================================================
// GLOBAL STATE
// ============================================================================
let currentEventSource = null;
let sessionId = null;
let currentThinkingBlock = null;
let currentAssistantMessage = null;
let currentPlanBlock = null;

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
    const chatContainer = document.getElementById('chatContainer');

    const messageEl = document.createElement('div');
    messageEl.className = 'message user';
    messageEl.innerHTML = `
        <div class="message-avatar">You</div>
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
            <!-- Plan, thinking, and answer will be added here -->
        </div>
    `;

    chatContainer.appendChild(messageEl);
    currentAssistantMessage = messageEl;
    scrollToBottom();

    return messageEl;
}

function addTypingIndicator() {
    if (!currentAssistantMessage) {
        addAssistantMessage();
    }

    const content = currentAssistantMessage.querySelector('.message-content');

    const typingEl = document.createElement('div');
    typingEl.className = 'typing-indicator';
    typingEl.innerHTML = `
        <div class="typing-dot"></div>
        <div class="typing-dot"></div>
        <div class="typing-dot"></div>
    `;

    content.appendChild(typingEl);
    scrollToBottom();

    return typingEl;
}

function removeTypingIndicator() {
    const typing = currentAssistantMessage?.querySelector('.typing-indicator');
    if (typing) {
        typing.remove();
    }
}

// ============================================================================
// PLAN BLOCK (Plan-and-Execute V2)
// ============================================================================
function createPlanBlock(planData) {
    if (!currentAssistantMessage) {
        addAssistantMessage();
    }

    removeTypingIndicator();

    const content = currentAssistantMessage.querySelector('.message-content');

    const planEl = document.createElement('div');
    planEl.className = 'plan-block';

    const stepsList = planData.steps.map((step, idx) => {
        const parallelIcon = step.can_parallel ? '⚡' : '➡️';
        const depsText = step.depends_on.length > 0 ? ` (depends on: ${step.depends_on.join(', ')})` : '';

        return `
            <div class="plan-step" data-step-id="${step.id}">
                <div class="plan-step-header">
                    <span class="plan-step-icon">${parallelIcon}</span>
                    <span class="plan-step-number">${step.id}.</span>
                    <span class="plan-step-description">${escapeHtml(step.description)}</span>
                </div>
                <div class="plan-step-meta">
                    <span class="plan-step-action">Action: ${step.action}</span>
                    <span class="plan-step-time">~${step.estimated_time}s</span>
                    ${depsText ? `<span class="plan-step-deps">${depsText}</span>` : ''}
                </div>
                <div class="plan-step-status">⏳ Pending</div>
            </div>
        `;
    }).join('');

    planEl.innerHTML = `
        <div class="plan-header" onclick="togglePlan(this)">
            <div class="plan-title">
                <svg class="plan-icon" viewBox="0 0 24 24" fill="none">
                    <path d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" stroke="currentColor" stroke-width="2"/>
                    <path d="M9 12l2 2 4-4" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
                </svg>
                <span>Plan: ${escapeHtml(planData.goal)}</span>
            </div>
            <span class="plan-meta">${planData.steps.length} steps, ~${planData.total_estimated_time}s</span>
            <svg class="plan-chevron" viewBox="0 0 24 24" fill="none">
                <path d="M6 9l6 6 6-6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
        </div>
        <div class="plan-content">
            <div class="plan-steps">${stepsList}</div>
        </div>
    `;

    content.appendChild(planEl);
    currentPlanBlock = planEl;
    scrollToBottom();

    return planEl;
}

function updateStepStatus(stepId, status, data = null) {
    if (!currentPlanBlock) return;

    const stepEl = currentPlanBlock.querySelector(`.plan-step[data-step-id="${stepId}"]`);
    if (!stepEl) return;

    const statusEl = stepEl.querySelector('.plan-step-status');

    if (status === 'running') {
        statusEl.innerHTML = '▶️ Running...';
        statusEl.className = 'plan-step-status running';
        stepEl.classList.add('active');
    } else if (status === 'completed') {
        const time = data?.execution_time ? ` (${data.execution_time.toFixed(1)}s)` : '';
        statusEl.innerHTML = `✅ Completed${time}`;
        statusEl.className = 'plan-step-status completed';
        stepEl.classList.remove('active');
        stepEl.classList.add('completed');
    } else if (status === 'failed') {
        const error = data?.error ? `: ${data.error.substring(0, 50)}...` : '';
        statusEl.innerHTML = `❌ Failed${error}`;
        statusEl.className = 'plan-step-status failed';
        stepEl.classList.remove('active');
        stepEl.classList.add('failed');
    }

    scrollToBottom();
}

function togglePlan(header) {
    const planBlock = header.closest('.plan-block');
    const content = planBlock.querySelector('.plan-content');
    const chevron = planBlock.querySelector('.plan-chevron');

    if (content.style.display === 'none') {
        content.style.display = 'block';
        chevron.style.transform = 'rotate(0deg)';
    } else {
        content.style.display = 'none';
        chevron.style.transform = 'rotate(-90deg)';
    }
}

// ============================================================================
// THINKING BLOCK
// ============================================================================
function createThinkingBlock(title = 'Processing...') {
    if (!currentAssistantMessage) {
        addAssistantMessage();
    }

    const content = currentAssistantMessage.querySelector('.message-content');

    const thinkingEl = document.createElement('div');
    thinkingEl.className = 'thinking-block';
    thinkingEl.innerHTML = `
        <div class="thinking-header" onclick="toggleThinking(this)">
            <div class="thinking-title">
                <svg class="thinking-icon spinning" viewBox="0 0 24 24" fill="none">
                    <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2" opacity="0.25"/>
                    <path d="M12 2a10 10 0 0 1 10 10" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
                </svg>
                <span>${title}</span>
            </div>
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
    stepEl.className = `thinking-step thinking-step-${type}`;
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
        title.textContent = 'Complete';
    }
}

function toggleThinking(header) {
    const thinkingBlock = header.closest('.thinking-block');
    const content = thinkingBlock.querySelector('.thinking-content');
    const chevron = thinkingBlock.querySelector('.thinking-chevron');

    if (content.style.display === 'none') {
        content.style.display = 'block';
        chevron.style.transform = 'rotate(0deg)';
    } else {
        content.style.display = 'none';
        chevron.style.transform = 'rotate(-90deg)';
    }
}

function getStepLabel(stepType) {
    const labels = {
        'routing': '🔀 Routing:',
        'planning': '📋 Planning:',
        'execution': '⚙️ Executing:',
        'reflection': '🔍 Reflecting:',
        'replan': '🔄 Replanning:'
    };
    return labels[stepType] || 'Step:';
}

// ============================================================================
// FINAL ANSWER
// ============================================================================
function addFinalAnswer(text) {
    if (!currentAssistantMessage) {
        addAssistantMessage();
    }

    removeTypingIndicator();

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
    currentPlanBlock = null;

    // Create URL
    const url = `/api/stream?q=${encodeURIComponent(query)}&session_id=${encodeURIComponent(sessionId)}`;

    try {
        currentEventSource = new EventSource(url);
        setupSSEListeners(currentEventSource);
    } catch (error) {
        console.error('Error creating EventSource:', error);
        addErrorMessage('Failed to connect to server');
        setInputEnabled(true);
    }
}

function setupSSEListeners(eventSource) {
    // Start event
    eventSource.addEventListener('start', (event) => {
        console.log('Agent started (Plan-and-Execute)');
        addTypingIndicator();
    });

    // Routing events
    eventSource.addEventListener('routing_start', (event) => {
        createThinkingBlock('Routing query...');
        addThinkingStep('routing', 'Analyzing query type...');
    });

    eventSource.addEventListener('routing_complete', (event) => {
        const data = JSON.parse(event.data);
        addThinkingStep('routing', `Route: ${data.route_type} (confidence: ${(data.confidence * 100).toFixed(0)}%)`);
    });

    // Simple answer (no agent needed)
    eventSource.addEventListener('simple_answer', (event) => {
        const data = JSON.parse(event.data);
        addFinalAnswer(data.answer);

        eventSource.close();
        currentEventSource = null;
        setInputEnabled(true);
    });

    // Planning events
    eventSource.addEventListener('planning_start', (event) => {
        removeTypingIndicator();
        createThinkingBlock('Creating plan...');
        addThinkingStep('planning', 'Analyzing task and creating execution plan...');
    });

    eventSource.addEventListener('plan_created', (event) => {
        const data = JSON.parse(event.data);
        removeTypingIndicator();
        finishThinking();
        createPlanBlock(data);
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
    });

    eventSource.addEventListener('reflection_complete', (event) => {
        const data = JSON.parse(event.data);
        console.log('Reflection:', data.status);
    });

    // Replan event
    eventSource.addEventListener('replan', (event) => {
        const data = JSON.parse(event.data);
        createThinkingBlock('Replanning...');
        addThinkingStep('replan', data.reason);
    });

    // Needs user input
    eventSource.addEventListener('needs_user_input', (event) => {
        const data = JSON.parse(event.data);
        const questions = data.questions.join('\n• ');
        addFinalAnswer(`I need more information:\n\n• ${questions}`);

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
                addErrorMessage(data.error || 'An error occurred');
            } catch (e) {
                addErrorMessage('An error occurred');
            }
        } else {
            if (eventSource.readyState === EventSource.CLOSED) {
                console.log('SSE connection closed');
            } else {
                addErrorMessage('Lost connection to server');
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

    removeTypingIndicator();

    const content = currentAssistantMessage.querySelector('.message-content');

    const errorEl = document.createElement('div');
    errorEl.className = 'message-text error';
    errorEl.style.color = '#ef4444';
    errorEl.textContent = `Error: ${text}`;

    content.appendChild(errorEl);
    scrollToBottom();
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
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
