// Chat App JavaScript with Real-Time Streaming

const API_BASE = '';

// Elements
const chatContainer = document.getElementById('chat-container');
const messageInput = document.getElementById('message-input');
const sendBtn = document.getElementById('send-btn');
const modelSelect = document.getElementById('model-select');
const agentToggle = document.getElementById('agent-toggle');
const resetBtn = document.getElementById('reset-btn');

// State
let isLoading = false;
let currentAgentLog = null;

// ============================================================
// MESSAGE RENDERING
// ============================================================

function addMessage(content, type = 'user') {
    const welcome = chatContainer.querySelector('.welcome-message');
    if (welcome) welcome.remove();

    const msg = document.createElement('div');
    msg.className = `message ${type}`;
    msg.textContent = content;
    chatContainer.appendChild(msg);
    scrollToBottom();
}

function createAgentLog() {
    const welcome = chatContainer.querySelector('.welcome-message');
    if (welcome) welcome.remove();

    const log = document.createElement('div');
    log.className = 'message agent-log';
    log.innerHTML = `
        <div class="agent-header">
            <span class="agent-icon">🤖</span> Agent Executing...
        </div>
        <div class="agent-events"></div>
    `;
    chatContainer.appendChild(log);
    currentAgentLog = log;
    scrollToBottom();
    return log;
}

function addAgentEvent(eventType, data) {
    if (!currentAgentLog) return;

    const eventsDiv = currentAgentLog.querySelector('.agent-events');
    const event = document.createElement('div');
    event.className = `agent-event event-${eventType}`;

    let icon = '▶';
    let text = '';

    switch (eventType) {
        case 'high_level_start':
            icon = '🎯';
            text = `Task: ${data.task}`;
            break;
        case 'planning':
            icon = '📋';
            text = 'Creating plan...';
            break;
        case 'plan_created':
            icon = '✓';
            text = `Plan: ${data.subtask_count} subtasks`;
            if (data.subtasks) {
                text += '<ul>' + data.subtasks.map(s =>
                    `<li><b>${s.id}.</b> [${s.agent_type}] ${s.instruction.slice(0, 60)}...</li>`
                ).join('') + '</ul>';
            }
            break;
        case 'subtask_start':
            icon = '🔧';
            text = `Subtask ${data.id}: ${data.instruction.slice(0, 50)}...`;
            break;
        case 'tool_start':
            icon = '⚙️';
            text = `<b>${data.tool}</b>(${JSON.stringify(data.args).slice(0, 40)}...)`;
            break;
        case 'tool_result':
            icon = data.success ? '✓' : '✗';
            text = `${data.tool}: ${data.success ? 'ok' : 'failed'}`;
            event.className += data.success ? ' success' : ' error';
            break;
        case 'subtask_complete':
            icon = data.success ? '✓' : '✗';
            text = `Subtask ${data.id}: ${data.success ? 'Complete' : 'Failed'}`;
            event.className += data.success ? ' success' : ' error';
            break;
        case 'high_level_complete':
            icon = data.success ? '🎉' : '❌';
            text = `<b>${data.success ? 'SUCCESS' : 'FAILED'}</b>: ${data.summary}`;
            break;
        default:
            text = JSON.stringify(data).slice(0, 100);
    }

    event.innerHTML = `<span class="event-icon">${icon}</span> ${text}`;
    eventsDiv.appendChild(event);
    scrollToBottom();
}

function finalizeAgentLog(result) {
    if (!currentAgentLog) return;

    const header = currentAgentLog.querySelector('.agent-header');
    header.innerHTML = result.success
        ? '<span class="agent-icon">✅</span> Agent Complete'
        : '<span class="agent-icon">❌</span> Agent Failed';

    currentAgentLog = null;
}

function addAgentReport(report) {
    const welcome = chatContainer.querySelector('.welcome-message');
    if (welcome) welcome.remove();

    const msg = document.createElement('div');
    msg.className = 'message agent-report';

    const statusClass = report.success ? 'success' : 'error';
    const statusText = report.success ? 'SUCCESS' : 'FAILED';

    let actionsHtml = '';
    if (report.actions && report.actions.length > 0) {
        actionsHtml = `
            <div class="actions-list">
                <strong>Actions (${report.actions.length}):</strong>
                ${report.actions.slice(0, 10).map(a => `
                    <div class="action-item">${a.tool || a.action}: ${JSON.stringify(a.args || {}).slice(0, 50)}</div>
                `).join('')}
            </div>
        `;
    }

    let screenshotsHtml = '';
    if (report.screenshots && report.screenshots.length > 0) {
        screenshotsHtml = `
            <div class="screenshots">
                ${report.screenshots.map(s => `
                    <img src="${s}" class="screenshot-thumb" onclick="window.open('${s}', '_blank')">
                `).join('')}
            </div>
        `;
    }

    msg.innerHTML = `
        <div class="report-header">
            <span class="status ${statusClass}">${statusText}</span>
            <span>Agent Report</span>
        </div>
        <div class="summary">${report.summary}</div>
        ${actionsHtml}
        ${screenshotsHtml}
    `;

    chatContainer.appendChild(msg);
    scrollToBottom();
}

function scrollToBottom() {
    chatContainer.scrollTop = chatContainer.scrollHeight;
}

// ============================================================
// API CALLS
// ============================================================

async function sendChat(message) {
    const model = modelSelect.value;

    const response = await fetch(`${API_BASE}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message, model })
    });

    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Chat failed');
    }

    return response.json();
}

async function sendAgentTaskStream(task) {
    const model = modelSelect.value;

    // Create log display
    createAgentLog();

    // Start SSE stream
    const url = `${API_BASE}/api/agent/stream?task=${encodeURIComponent(task)}&model=${encodeURIComponent(model)}`;
    const eventSource = new EventSource(url);

    return new Promise((resolve, reject) => {
        eventSource.onmessage = (e) => {
            try {
                const event = JSON.parse(e.data);

                if (event.type === 'heartbeat') return;

                if (event.type === 'complete') {
                    finalizeAgentLog(event.data);
                    eventSource.close();
                    resolve(event.data);
                } else {
                    addAgentEvent(event.type, event.data);
                }
            } catch (err) {
                console.error('Event parse error:', err);
            }
        };

        eventSource.onerror = (e) => {
            console.error('SSE error:', e);
            eventSource.close();
            reject(new Error('Stream connection failed'));
        };
    });
}

async function sendAgentTask(task) {
    const model = modelSelect.value;

    const response = await fetch(`${API_BASE}/api/agent`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ task, model })
    });

    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Agent failed');
    }

    return response.json();
}

async function resetChat() {
    await fetch(`${API_BASE}/api/reset`, { method: 'POST' });
    chatContainer.innerHTML = `
        <div class="welcome-message">
            <p>Start a conversation or enable <strong>Agent Mode</strong> to execute tasks.</p>
        </div>
    `;
}

// ============================================================
// EVENT HANDLERS
// ============================================================

async function handleSend() {
    const message = messageInput.value.trim();
    if (!message || isLoading) return;

    messageInput.value = '';
    messageInput.style.height = 'auto';

    addMessage(message, 'user');

    isLoading = true;
    sendBtn.disabled = true;

    try {
        if (agentToggle.checked) {
            // Agent mode - use SSE streaming
            await streamAgentTask(message);
        } else {
            // Chat mode
            const loading = document.createElement('div');
            loading.className = 'loading';
            loading.id = 'loading';
            loading.innerHTML = '<span></span><span></span><span></span>';
            chatContainer.appendChild(loading);
            scrollToBottom();

            const result = await sendChat(message);

            const loadingEl = document.getElementById('loading');
            if (loadingEl) loadingEl.remove();

            addMessage(result.response, 'assistant');
        }
    } catch (error) {
        const loadingEl = document.getElementById('loading');
        if (loadingEl) loadingEl.remove();
        addMessage(`Error: ${error.message}`, 'assistant');
    }

    isLoading = false;
    sendBtn.disabled = false;
    messageInput.focus();
}

// Stream agent task with SSE
async function streamAgentTask(task) {
    const model = modelSelect.value;

    // Create streaming message container
    const msgDiv = document.createElement('div');
    msgDiv.className = 'message assistant agent-report';
    msgDiv.innerHTML = `
        <div class="agent-header">
            <span class="agent-icon">🤖</span>
            <span>Agent Streaming...</span>
        </div>
        <details class="thinking-section" open>
            <summary>💭 Thinking</summary>
            <div class="thinking-content"></div>
        </details>
        <details class="actions-section" open>
            <summary>⚡ Actions</summary>
            <div class="actions-content"></div>
        </details>
        <div class="summary-section" style="display:none;"></div>
    `;
    chatContainer.appendChild(msgDiv);
    scrollToBottom();

    const thinkingContent = msgDiv.querySelector('.thinking-content');
    const actionsContent = msgDiv.querySelector('.actions-content');
    const summarySection = msgDiv.querySelector('.summary-section');

    return new Promise((resolve, reject) => {
        const eventSource = new EventSource(
            `/api/agent/stream?task=${encodeURIComponent(task)}&model=${encodeURIComponent(model)}`
        );

        eventSource.onmessage = (e) => {
            try {
                const event = JSON.parse(e.data);

                switch (event.type) {
                    case 'thinking_start':
                        // Clear any placeholder
                        break;

                    case 'thinking_delta':
                        thinkingContent.textContent += event.content;
                        scrollToBottom();
                        break;

                    case 'step_start':
                        // Add step indicator
                        break;

                    case 'action_start':
                        const actionStart = document.createElement('div');
                        actionStart.className = 'action-item action-pending';
                        actionStart.innerHTML = `<span class="action-icon">⏳</span> ${event.tool}(${JSON.stringify(event.args).slice(0, 50)}...)`;
                        actionsContent.appendChild(actionStart);
                        scrollToBottom();
                        break;

                    case 'action_result':
                        // Update last action with result
                        const lastAction = actionsContent.querySelector('.action-pending:last-child');
                        if (lastAction) {
                            lastAction.className = event.success ? 'action-item action-success' : 'action-item action-failed';
                            lastAction.innerHTML = `
                                <span class="action-icon">${event.success ? '✅' : '❌'}</span>
                                <strong>${event.tool}</strong>
                                <div class="action-result">${event.result}</div>
                            `;
                        }
                        scrollToBottom();
                        break;

                    case 'complete':
                    case 'done':
                        summarySection.style.display = 'block';
                        summarySection.innerHTML = `
                            <div class="summary ${event.success ? 'success' : 'failed'}">
                                ${event.success ? '✅' : '❌'} ${event.summary || 'Task completed'}
                            </div>
                        `;
                        msgDiv.querySelector('.agent-header span:last-child').textContent = 'Agent Complete';
                        eventSource.close();
                        resolve(event);
                        break;

                    case 'error':
                        summarySection.style.display = 'block';
                        summarySection.innerHTML = `<div class="summary failed">❌ Error: ${event.message}</div>`;
                        eventSource.close();
                        reject(new Error(event.message));
                        break;
                }
            } catch (err) {
                console.error('Parse error:', err);
            }
        };

        eventSource.onerror = (e) => {
            console.error('SSE error:', e);
            eventSource.close();
            summarySection.style.display = 'block';
            summarySection.innerHTML = `<div class="summary failed">❌ Connection error</div>`;
            reject(new Error('Connection error'));
        };
    });
}

// Send on button click
sendBtn.addEventListener('click', handleSend);

// Send on Enter (Shift+Enter for newline)
messageInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSend();
    }
});

// Auto-resize textarea
messageInput.addEventListener('input', () => {
    messageInput.style.height = 'auto';
    messageInput.style.height = Math.min(messageInput.scrollHeight, 150) + 'px';
});

// Reset button
resetBtn.addEventListener('click', resetChat);

// Update placeholder based on mode
agentToggle.addEventListener('change', () => {
    if (agentToggle.checked) {
        messageInput.placeholder = 'Enter a task for the agent...';
    } else {
        messageInput.placeholder = 'Type a message...';
    }
});

// Focus input on load
messageInput.focus();
