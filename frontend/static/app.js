/**
 * Travel Agent MVP - Frontend JavaScript
 * Handles SSE streaming, UI updates, and user interactions
 */

// ============================================================================
// GLOBAL STATE
// ============================================================================
let currentEventSource = null;
let sessionId = null;

// ============================================================================
// INITIALIZATION
// ============================================================================
document.addEventListener('DOMContentLoaded', () => {
    console.log('Travel Agent MVP initialized');

    // Initialize session ID
    sessionId = getSessionId();

    // Setup keyboard shortcuts
    setupKeyboardShortcuts();

    // Auto-focus on textarea
    document.getElementById('queryInput').focus();
});

// ============================================================================
// SESSION MANAGEMENT
// ============================================================================
function getSessionId() {
    // Get or create session ID from sessionStorage
    let id = sessionStorage.getItem('travel_agent_session_id');

    if (!id) {
        id = `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
        sessionStorage.setItem('travel_agent_session_id', id);
    }

    return id;
}

// ============================================================================
// MAIN QUERY SUBMISSION
// ============================================================================
async function submitQuery() {
    const queryInput = document.getElementById('queryInput');
    const query = queryInput.value.trim();

    // Validation
    if (!query) {
        alert('Пожалуйста, введите ваш запрос');
        queryInput.focus();
        return;
    }

    // Disable input during processing
    setInputEnabled(false);

    // Clear previous results
    clearResults();

    // Show loading indicator
    showLoading(true);

    // Close any existing SSE connection
    if (currentEventSource) {
        currentEventSource.close();
    }

    // Create SSE connection
    const url = `/api/stream?q=${encodeURIComponent(query)}&session_id=${encodeURIComponent(sessionId)}`;

    try {
        currentEventSource = new EventSource(url);

        // Setup event listeners
        setupSSEEventListeners(currentEventSource);

    } catch (error) {
        console.error('Error creating EventSource:', error);
        showError('Не удалось установить соединение с сервером');
        setInputEnabled(true);
        showLoading(false);
    }
}

// ============================================================================
// SSE EVENT LISTENERS
// ============================================================================
function setupSSEEventListeners(eventSource) {
    // Start event
    eventSource.addEventListener('start', (event) => {
        console.log('Agent started:', event.data);
        const data = JSON.parse(event.data);
        showLoading(false);
        showReasoningSection(true);

        addReasoningStep({
            step_type: 'start',
            content: data.message,
            timestamp: data.timestamp,
            metadata: data
        });
    });

    // Think step
    eventSource.addEventListener('think', (event) => {
        const step = JSON.parse(event.data);
        addReasoningStep(step);
    });

    // Act step
    eventSource.addEventListener('act', (event) => {
        const step = JSON.parse(event.data);
        addReasoningStep(step);
    });

    // Observe step
    eventSource.addEventListener('observe', (event) => {
        const step = JSON.parse(event.data);
        addReasoningStep(step);
    });

    // Done event - final answer
    eventSource.addEventListener('done', (event) => {
        const step = JSON.parse(event.data);
        addReasoningStep(step);
        showFinalAnswer(step.content);

        // Cleanup
        eventSource.close();
        currentEventSource = null;
        setInputEnabled(true);
        showLoading(false);
    });

    // Error event
    eventSource.addEventListener('error', (event) => {
        console.error('SSE Error:', event);

        if (event.data) {
            try {
                const errorData = JSON.parse(event.data);
                showError(errorData.content || 'Произошла ошибка');
                addReasoningStep(errorData);
            } catch (e) {
                showError('Произошла ошибка при обработке запроса');
            }
        } else {
            // Connection error
            if (eventSource.readyState === EventSource.CLOSED) {
                console.log('SSE connection closed');
            } else {
                showError('Потеряно соединение с сервером');
            }
        }

        // Cleanup
        eventSource.close();
        currentEventSource = null;
        setInputEnabled(true);
        showLoading(false);
    });
}

// ============================================================================
// UI UPDATES
// ============================================================================
function addReasoningStep(step) {
    const reasoningSteps = document.getElementById('reasoningSteps');

    // Create step element
    const stepElement = document.createElement('div');
    stepElement.className = `reasoning-step ${step.step_type}`;

    // Get icon for step type
    const icon = getStepIcon(step.step_type);

    // Format timestamp
    const timestamp = formatTimestamp(step.timestamp);

    // Build step HTML
    stepElement.innerHTML = `
        <div class="step-header">
            <span class="step-icon">${icon}</span>
            <span class="step-type">${step.step_type}</span>
            <span class="step-timestamp">${timestamp}</span>
        </div>
        <div class="step-content">${escapeHtml(step.content)}</div>
        ${step.metadata ? formatMetadata(step.metadata) : ''}
    `;

    // Add to container
    reasoningSteps.appendChild(stepElement);

    // Auto-scroll to bottom
    stepElement.scrollIntoView({ behavior: 'smooth', block: 'end' });
}

function showFinalAnswer(content) {
    const finalAnswerSection = document.getElementById('finalAnswerSection');
    const finalAnswerContent = document.getElementById('finalAnswerContent');

    finalAnswerContent.textContent = content;
    finalAnswerSection.style.display = 'block';

    // Smooth scroll to final answer
    setTimeout(() => {
        finalAnswerSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 300);
}

function showReasoningSection(show) {
    const reasoningSection = document.getElementById('reasoningSection');
    reasoningSection.style.display = show ? 'block' : 'none';
}

function showLoading(show) {
    const loadingIndicator = document.getElementById('loadingIndicator');
    loadingIndicator.style.display = show ? 'flex' : 'none';
}

function setInputEnabled(enabled) {
    const queryInput = document.getElementById('queryInput');
    const submitBtn = document.getElementById('submitBtn');

    queryInput.disabled = !enabled;
    submitBtn.disabled = !enabled;

    if (enabled) {
        submitBtn.querySelector('.button-text').textContent = 'Отправить';
    } else {
        submitBtn.querySelector('.button-text').textContent = 'Обработка...';
    }
}

function clearResults() {
    // Clear reasoning steps
    const reasoningSteps = document.getElementById('reasoningSteps');
    reasoningSteps.innerHTML = '';

    // Hide sections
    document.getElementById('reasoningSection').style.display = 'none';
    document.getElementById('finalAnswerSection').style.display = 'none';

    // Clear final answer
    document.getElementById('finalAnswerContent').textContent = '';
}

function showError(message) {
    const reasoningSteps = document.getElementById('reasoningSteps');

    const errorElement = document.createElement('div');
    errorElement.className = 'reasoning-step error';
    errorElement.innerHTML = `
        <div class="step-header">
            <span class="step-icon">❌</span>
            <span class="step-type">ERROR</span>
            <span class="step-timestamp">${formatTimestamp(new Date().toISOString())}</span>
        </div>
        <div class="step-content">${escapeHtml(message)}</div>
    `;

    reasoningSteps.appendChild(errorElement);

    // Show reasoning section if hidden
    showReasoningSection(true);

    // Auto-scroll
    errorElement.scrollIntoView({ behavior: 'smooth' });
}

// ============================================================================
// HELPER FUNCTIONS
// ============================================================================
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

function formatTimestamp(isoString) {
    if (!isoString) return '';

    try {
        const date = new Date(isoString);
        return date.toLocaleTimeString('ru-RU', {
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit'
        });
    } catch (e) {
        return '';
    }
}

function formatMetadata(metadata) {
    if (!metadata || Object.keys(metadata).length === 0) {
        return '';
    }

    // Filter out certain keys
    const filtered = { ...metadata };
    delete filtered.session_id;

    if (Object.keys(filtered).length === 0) {
        return '';
    }

    // Format as readable text
    let html = '<div class="step-metadata">';

    if (filtered.tool_name) {
        html += `<div><span class="metadata-label">Инструмент:</span> ${escapeHtml(filtered.tool_name)}</div>`;
    }

    if (filtered.tool_args) {
        html += `<div><span class="metadata-label">Параметры:</span> ${escapeHtml(JSON.stringify(filtered.tool_args, null, 2))}</div>`;
    }

    if (filtered.tool_result) {
        const resultStr = JSON.stringify(filtered.tool_result, null, 2);
        // Truncate if too long
        const truncated = resultStr.length > 500 ? resultStr.substring(0, 500) + '...' : resultStr;
        html += `<div><span class="metadata-label">Результат:</span> <pre style="margin-top: 0.5rem; padding: 0.5rem; background: #f8f9fa; border-radius: 4px; overflow-x: auto;">${escapeHtml(truncated)}</pre></div>`;
    }

    if (filtered.iterations) {
        html += `<div><span class="metadata-label">Итераций:</span> ${filtered.iterations}</div>`;
    }

    html += '</div>';

    return html;
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
// EXAMPLE QUERIES
// ============================================================================
function setExampleQuery(query) {
    const queryInput = document.getElementById('queryInput');
    queryInput.value = query;
    queryInput.focus();

    // Optionally, auto-submit
    // submitQuery();
}

// ============================================================================
// KEYBOARD SHORTCUTS
// ============================================================================
function setupKeyboardShortcuts() {
    const queryInput = document.getElementById('queryInput');

    queryInput.addEventListener('keydown', (event) => {
        // Enter without Shift = submit
        if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            submitQuery();
        }

        // Shift + Enter = new line (default behavior)
    });
}

// ============================================================================
// UTILITIES
// ============================================================================
function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(() => {
        console.log('Copied to clipboard');
    }).catch(err => {
        console.error('Failed to copy:', err);
    });
}

// ============================================================================
// EXPORT FOR TESTING
// ============================================================================
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        submitQuery,
        addReasoningStep,
        showFinalAnswer,
        getStepIcon,
        formatTimestamp,
        escapeHtml
    };
}
