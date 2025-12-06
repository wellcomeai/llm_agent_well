/**
 * Travel Agent - Premium Chat Interface
 * Clean, minimal, world-class UX
 */

// ============================================================================
// GLOBAL STATE
// ============================================================================
let currentEventSource = null;
let sessionId = null;
let currentThinkingBlock = null;
let currentAssistantMessage = null;

// ============================================================================
// INITIALIZATION
// ============================================================================
document.addEventListener('DOMContentLoaded', () => {
    console.log('Travel Agent Premium UI initialized');

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
            <!-- Thinking block will be added here -->
            <!-- Final answer will be added here -->
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
// THINKING BLOCK (Premium Design)
// ============================================================================
function createThinkingBlock() {
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
                <span>Thinking...</span>
            </div>
            <svg class="thinking-chevron" viewBox="0 0 24 24" fill="none">
                <path d="M6 9l6 6 6-6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
        </div>
        <div class="thinking-content">
            <div class="thinking-steps"></div>
        </div>
    `;

    content.insertBefore(thinkingEl, content.firstChild);
    currentThinkingBlock = thinkingEl;
    scrollToBottom();

    return thinkingEl;
}

function addThinkingStep(stepType, content) {
    if (!currentThinkingBlock) {
        createThinkingBlock();
    }

    const stepsContainer = currentThinkingBlock.querySelector('.thinking-steps');
    
    const stepEl = document.createElement('div');
    stepEl.className = `thinking-step ${stepType}`;
    
    const label = getStepLabel(stepType);
    stepEl.innerHTML = `
        <span class="thinking-step-label">${label}</span>
        ${escapeHtml(content)}
    `;

    stepsContainer.appendChild(stepEl);
    scrollToBottom();
}

function finishThinking() {
    if (!currentThinkingBlock) return;

    // Stop spinning icon
    const icon = currentThinkingBlock.querySelector('.thinking-icon');
    icon.classList.remove('spinning');
    icon.innerHTML = `
        <path d="M20 6L9 17l-5-5" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
    `;

    // Update title
    const title = currentThinkingBlock.querySelector('.thinking-title span');
    title.textContent = 'Thought process';

    // Collapse by default (premium UX)
    currentThinkingBlock.classList.add('collapsed');
}

function toggleThinking(headerEl) {
    const block = headerEl.closest('.thinking-block');
    block.classList.toggle('collapsed');
}

function getStepLabel(stepType) {
    const labels = {
        'act': 'Action:',
        'observe': 'Result:',
        'think': 'Analysis:'
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
// SSE STREAMING
// ============================================================================
function startStreaming(query) {
    // Close existing connection
    if (currentEventSource) {
        currentEventSource.close();
    }

    // Reset state
    currentThinkingBlock = null;
    currentAssistantMessage = null;

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
        console.log('Agent started');
        addTypingIndicator();
    });

    // Act event (tool call)
    eventSource.addEventListener('act', (event) => {
        const data = JSON.parse(event.data);
        addThinkingStep('act', data.content);
    });

    // Observe event (tool result)
    eventSource.addEventListener('observe', (event) => {
        const data = JSON.parse(event.data);
        addThinkingStep('observe', data.content);
    });

    // Done event (final answer)
    eventSource.addEventListener('done', (event) => {
        const data = JSON.parse(event.data);
        addFinalAnswer(data.content);

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
                addErrorMessage(data.content);
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
    errorEl.className = 'message-text';
    errorEl.style.color = '#ef4444';
    errorEl.textContent = text;

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
    setTimeout(() => {
        chatContainer.scrollTo({
            top: chatContainer.scrollHeight,
            behavior: 'smooth'
        });
    }, 100);
}

function escapeHtml(text) {
    if (typeof text !== 'string') {
        text = String(text);
    }
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// ============================================================================
// EXPORT (for testing)
// ============================================================================
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        sendMessage,
        addUserMessage,
        addAssistantMessage,
        addThinkingStep,
        addFinalAnswer
    };
}
