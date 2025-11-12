/**
 * Travel Agent - ChatGPT Style UI
 * Clean, minimal chat interface with SSE streaming
 * 
 * 🔧 FIXED: Race condition, unique message IDs, proper state management
 */

// ============================================================================
// GLOBAL STATE
// ============================================================================
let currentEventSource = null;
let sessionId = null;
let startTime = null;
let isProcessing = false;  // 🔧 NEW: Prevent parallel requests
let currentMessageId = null;  // 🔧 NEW: Track current message being processed

// ============================================================================
// INITIALIZATION
// ============================================================================
document.addEventListener('DOMContentLoaded', () => {
    console.log('Travel Agent ChatGPT UI initialized');

    // Initialize session ID
    sessionId = getSessionId();

    // Auto-focus on input
    document.getElementById('userInput').focus();
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
// WELCOME MESSAGE
// ============================================================================
function showWelcomeMessage() {
    const welcome = document.getElementById('welcomeMessage');
    if (welcome) {
        welcome.style.display = 'block';
    }
}

function hideWelcomeMessage() {
    const welcome = document.getElementById('welcomeMessage');
    if (welcome) {
        welcome.style.display = 'none';
    }
}

// ============================================================================
// EXAMPLE PROMPTS
// ============================================================================
function useExamplePrompt(button) {
    const prompt = button.getAttribute('data-prompt');
    const input = document.getElementById('userInput');
    input.value = prompt;
    input.focus();
    handleInputChange();

    // Auto-submit after a short delay
    setTimeout(() => {
        sendMessage();
    }, 300);
}

// ============================================================================
// INPUT HANDLING
// ============================================================================
function handleInputChange() {
    const input = document.getElementById('userInput');
    const sendBtn = document.getElementById('sendBtn');

    // Enable/disable send button based on input and processing state
    sendBtn.disabled = !input.value.trim() || isProcessing;

    // Auto-resize textarea
    autoResizeTextarea();
}

function autoResizeTextarea() {
    const textarea = document.getElementById('userInput');
    textarea.style.height = 'auto';
    textarea.style.height = Math.min(textarea.scrollHeight, 200) + 'px';
}

function handleKeyDown(event) {
    // Enter without Shift = send message
    if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        sendMessage();
    }
    // Shift + Enter = new line (default behavior)
}

// ============================================================================
// MESSAGE SENDING
// ============================================================================
async function sendMessage() {
    const input = document.getElementById('userInput');
    const message = input.value.trim();

    if (!message) {
        return;
    }

    // 🔧 FIXED: Prevent parallel requests
    if (isProcessing) {
        console.warn('⚠️  Already processing a message, please wait');
        return;
    }

    console.log('📤 [SEND] Starting new message:', message);

    // Set processing flag
    isProcessing = true;

    // Hide welcome message
    hideWelcomeMessage();

    // Add user message to chat
    addUserMessage(message);

    // Clear input
    input.value = '';
    input.style.height = 'auto';
    handleInputChange();

    // Disable input during processing
    setInputEnabled(false);

    // 🔧 FIXED: Properly close previous connection
    if (currentEventSource) {
        console.log('🧹 [SEND] Closing previous SSE connection');
        currentEventSource.close();
        currentEventSource = null;
    }

    // 🔧 FIXED: Clear previous message ID
    currentMessageId = null;

    // Create SSE connection
    const url = `/api/stream?q=${encodeURIComponent(message)}&session_id=${encodeURIComponent(sessionId)}`;

    try {
        currentEventSource = new EventSource(url);
        setupSSEEventListeners(currentEventSource);
    } catch (error) {
        console.error('❌ [SEND] Error creating EventSource:', error);
        showError('Не удалось установить соединение с сервером');
        setInputEnabled(true);
        isProcessing = false;
    }
}

// ============================================================================
// MESSAGE DISPLAY
// ============================================================================
function addUserMessage(text) {
    const messagesWrapper = document.getElementById('messagesWrapper');
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message user-message';
    messageDiv.innerHTML = `
        <div class="message-avatar">👤</div>
        <div class="message-content">
            <div class="message-text">${escapeHtml(text)}</div>
        </div>
    `;
    messagesWrapper.appendChild(messageDiv);
    scrollToBottom();
    
    console.log('💬 [UI] User message added');
}

// 🔧 FIXED: Generate and store unique message ID
function addAssistantMessage() {
    const messagesWrapper = document.getElementById('messagesWrapper');
    
    // 🔧 Generate unique message ID
    const messageId = `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    currentMessageId = messageId;
    
    console.log(`💬 [UI] Creating assistant message with ID: ${messageId}`);
    
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message assistant-message';
    messageDiv.dataset.messageId = messageId;  // Store ID in data attribute
    
    messageDiv.innerHTML = `
        <div class="message-avatar">🤖</div>
        <div class="message-content">
            <div class="thinking-section collapsed">
                <div class="thinking-header" onclick="toggleThinking(this)">
                    <span class="thinking-icon">▶</span>
                    <span class="thinking-text">Thinking...</span>
                    <span class="thinking-time">0s</span>
                </div>
                <div class="thinking-steps"></div>
            </div>
            <div class="message-text" style="display:none;"></div>
        </div>
    `;
    
    messagesWrapper.appendChild(messageDiv);
    scrollToBottom();
    
    console.log(`✅ [UI] Assistant message created: ${messageId}`);
    return messageDiv;
}

// 🔧 FIXED: Target specific message by ID
function updateThinkingSteps(step) {
    if (!currentMessageId) {
        console.error('❌ [UI] No current message ID set');
        return;
    }
    
    const currentMessage = document.querySelector(`[data-message-id="${currentMessageId}"]`);
    if (!currentMessage) {
        console.error(`❌ [UI] Message not found: ${currentMessageId}`);
        return;
    }
    
    const thinkingSteps = currentMessage.querySelector('.thinking-steps');
    if (!thinkingSteps) {
        console.error(`❌ [UI] Thinking steps container not found in message: ${currentMessageId}`);
        return;
    }

    const stepDiv = document.createElement('div');
    stepDiv.className = `react-step ${step.step_type}`;
    const icon = getStepIcon(step.step_type);
    
    stepDiv.innerHTML = `
        <span class="step-icon">${icon}</span>
        <span class="step-text">${escapeHtml(step.content)}</span>
    `;

    thinkingSteps.appendChild(stepDiv);

    // Update step count
    const thinkingText = currentMessage.querySelector('.thinking-text');
    const stepCount = thinkingSteps.children.length;
    if (thinkingText) {
        thinkingText.textContent = `Thinking... (${stepCount} steps)`;
    }

    scrollToBottom();
    
    console.log(`📝 [UI] Step added to message ${currentMessageId}:`, step.step_type);
}

// 🔧 FIXED: Target specific message by ID
function showFinalResponse(text) {
    console.log('💬 [UI] showFinalResponse called with text length:', text?.length || 0);
    console.log('💬 [UI] Current message ID:', currentMessageId);

    if (!currentMessageId) {
        console.error('❌ [UI] No current message ID set');
        return;
    }

    const currentMessage = document.querySelector(`[data-message-id="${currentMessageId}"]`);
    if (!currentMessage) {
        console.error(`❌ [UI] Message not found: ${currentMessageId}`);
        return;
    }
    
    const assistantText = currentMessage.querySelector('.message-text');
    if (assistantText) {
        console.log(`✅ [UI] Setting text for message ${currentMessageId}`);
        assistantText.textContent = text;
        assistantText.style.display = 'block';
    } else {
        console.error(`❌ [UI] message-text element not found in message: ${currentMessageId}`);
    }

    scrollToBottom();
    
    console.log(`✅ [UI] Final response displayed for message ${currentMessageId}`);
}

// ============================================================================
// THINKING SECTION TOGGLE
// ============================================================================
function toggleThinking(header) {
    const section = header.closest('.thinking-section');
    if (section) {
        section.classList.toggle('collapsed');
    }
}

// ============================================================================
// SSE EVENT LISTENERS
// ============================================================================
function setupSSEEventListeners(eventSource) {
    eventSource.onopen = () => {
        console.log('✅ [SSE] Connection opened');
    };

    // Start event
    eventSource.addEventListener('start', (event) => {
        console.log('📥 [SSE] Received START event:', event.data);
        startTime = Date.now();

        // 🔧 Create assistant message container
        addAssistantMessage();

        const data = JSON.parse(event.data);
        updateThinkingSteps({
            step_type: 'start',
            content: data.message || 'Processing query...'
        });
    });

    // Think step
    eventSource.addEventListener('think', (event) => {
        console.log('📥 [SSE] Received THINK event:', event.data);
        const step = JSON.parse(event.data);
        updateThinkingSteps({
            step_type: 'start',
            content: step.content || 'Thinking...'
        });
    });

    // Act step
    eventSource.addEventListener('act', (event) => {
        console.log('📥 [SSE] Received ACT event:', event.data);
        const step = JSON.parse(event.data);
        updateThinkingSteps({
            step_type: 'act',
            content: step.content || 'Taking action...'
        });
    });

    // Observe step
    eventSource.addEventListener('observe', (event) => {
        console.log('📥 [SSE] Received OBSERVE event:', event.data);
        const step = JSON.parse(event.data);
        updateThinkingSteps({
            step_type: 'observe',
            content: step.content || 'Observing results...'
        });
    });

    // Done event - final answer
    eventSource.addEventListener('done', (event) => {
        console.log('📥 [SSE] Received DONE event:', event.data);
        const step = JSON.parse(event.data);

        console.log('📥 [SSE] DONE content length:', step.content?.length || 0);

        updateThinkingSteps({
            step_type: 'done',
            content: 'Response generated'
        });

        showFinalResponse(step.content);

        // Update timing
        if (startTime && currentMessageId) {
            const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
            const currentMessage = document.querySelector(`[data-message-id="${currentMessageId}"]`);
            if (currentMessage) {
                const timeElement = currentMessage.querySelector('.thinking-time');
                if (timeElement) {
                    timeElement.textContent = `${elapsed}s`;
                }
            }
        }

        // 🔧 FIXED: Proper cleanup
        console.log('✅ [SSE] Closing connection');
        eventSource.close();
        currentEventSource = null;
        currentMessageId = null;  // Clear message ID
        isProcessing = false;  // Reset processing flag
        setInputEnabled(true);
    });

    // Error event
    eventSource.addEventListener('error', (event) => {
        console.error('❌ [SSE] Error event:', event);
        console.error('❌ [SSE] ReadyState:', eventSource.readyState);

        if (event.data) {
            try {
                console.error('❌ [SSE] Error data:', event.data);
                const errorData = JSON.parse(event.data);
                showError(errorData.content || 'Произошла ошибка');
            } catch (e) {
                console.error('❌ [SSE] Failed to parse error data:', e);
                showError('Произошла ошибка при обработке запроса');
            }
        } else {
            if (eventSource.readyState === EventSource.CLOSED) {
                console.log('⚠️  [SSE] Connection closed');
            } else {
                console.error('❌ [SSE] Connection error, state:', eventSource.readyState);
                showError('Потеряно соединение с сервером');
            }
        }

        // 🔧 FIXED: Proper cleanup on error
        console.log('🧹 [SSE] Cleaning up after error');
        eventSource.close();
        currentEventSource = null;
        currentMessageId = null;
        isProcessing = false;
        setInputEnabled(true);
    });

    eventSource.onmessage = (event) => {
        console.log('📥 [SSE] Received unhandled message event:', event);
    };
}

// ============================================================================
// ERROR HANDLING
// ============================================================================
function showError(message) {
    console.error('🔴 [ERROR] Showing error:', message);
    
    // Try to add error to current message if exists
    if (currentMessageId) {
        const currentMessage = document.querySelector(`[data-message-id="${currentMessageId}"]`);
        if (currentMessage) {
            updateThinkingSteps({
                step_type: 'error',
                content: message
            });
            return;
        }
    }
    
    // Otherwise create new error message
    const messagesWrapper = document.getElementById('messagesWrapper');
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message assistant-message';
    messageDiv.innerHTML = `
        <div class="message-avatar">🤖</div>
        <div class="message-content">
            <div class="message-text" style="color: var(--color-error);">❌ ${escapeHtml(message)}</div>
        </div>
    `;
    messagesWrapper.appendChild(messageDiv);
    scrollToBottom();
}

// ============================================================================
// UTILITY FUNCTIONS
// ============================================================================
function setInputEnabled(enabled) {
    const input = document.getElementById('userInput');
    const sendBtn = document.getElementById('sendBtn');

    input.disabled = !enabled;

    if (enabled) {
        input.focus();
        handleInputChange(); // Re-check if button should be enabled
    } else {
        sendBtn.disabled = true;
    }
}

function scrollToBottom() {
    setTimeout(() => {
        window.scrollTo({
            top: document.body.scrollHeight,
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

function getStepIcon(stepType) {
    const icons = {
        'start': '🚀',
        'think': '🤔',
        'act': '🔧',
        'observe': '👀',
        'done': '✅',
        'error': '❌'
    };
    return icons[stepType] || '📌';
}

// ============================================================================
// CLEAR CHAT
// ============================================================================
function clearChat() {
    // Confirm before clearing
    if (!confirm('Вы уверены, что хотите очистить чат?')) {
        return;
    }

    console.log('🗑️  [CLEAR] Clearing chat');

    const messagesWrapper = document.getElementById('messagesWrapper');

    // Remove all messages
    const messages = messagesWrapper.querySelectorAll('.message');
    messages.forEach(msg => msg.remove());

    // Show welcome message
    showWelcomeMessage();

    // Clear session
    sessionStorage.removeItem('travel_agent_session_id');
    sessionId = getSessionId();

    // Close any active connections
    if (currentEventSource) {
        currentEventSource.close();
        currentEventSource = null;
    }

    // Reset state
    currentMessageId = null;
    isProcessing = false;

    // Reset input
    const input = document.getElementById('userInput');
    input.value = '';
    input.style.height = 'auto';
    input.focus();
    handleInputChange();

    console.log('✅ [CLEAR] Chat cleared, new session:', sessionId);
}

// ============================================================================
// EXPORT CHAT
// ============================================================================
function exportChat() {
    const messagesWrapper = document.getElementById('messagesWrapper');
    const messages = messagesWrapper.querySelectorAll('.message');

    if (messages.length === 0) {
        alert('Нет сообщений для экспорта');
        return;
    }

    let exportText = '# Travel Agent Chat Export\n\n';
    exportText += `Date: ${new Date().toLocaleString('ru-RU')}\n`;
    exportText += `Session ID: ${sessionId}\n\n`;
    exportText += '---\n\n';

    messages.forEach((msg, index) => {
        const isUser = msg.classList.contains('user-message');
        const messageText = msg.querySelector('.message-text');

        if (messageText) {
            const text = messageText.textContent.trim();
            exportText += `## ${isUser ? '👤 User' : '🤖 Assistant'}\n\n`;
            exportText += `${text}\n\n`;

            // Add thinking steps for assistant messages
            if (!isUser) {
                const thinkingSteps = msg.querySelectorAll('.react-step');
                if (thinkingSteps.length > 0) {
                    exportText += `### Thinking Process:\n\n`;
                    thinkingSteps.forEach(step => {
                        const stepText = step.querySelector('.step-text');
                        if (stepText) {
                            exportText += `- ${stepText.textContent.trim()}\n`;
                        }
                    });
                    exportText += '\n';
                }
            }

            exportText += '---\n\n';
        }
    });

    // Download as markdown file
    const blob = new Blob([exportText], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `travel-chat-${Date.now()}.md`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);

    console.log('💾 [EXPORT] Chat exported');
}

// ============================================================================
// EXPORT FOR TESTING (if needed)
// ============================================================================
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        sendMessage,
        addUserMessage,
        addAssistantMessage,
        clearChat,
        exportChat,
        toggleThinking,
        getStepIcon,
        escapeHtml
    };
}
