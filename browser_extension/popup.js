const statusDot = document.getElementById("status-dot");
const statusText = document.getElementById("status-text");
const detailText = document.getElementById("detail-text");
const serverValue = document.getElementById("server-value");
const socketValue = document.getElementById("socket-value");
const heartbeatValue = document.getElementById("heartbeat-value");
const reconnectButton = document.getElementById("reconnect-button");

function formatRelativeTime(timestamp) {
    if (!timestamp) {
        return "never";
    }

    const deltaSeconds = Math.max(0, Math.floor((Date.now() - timestamp) / 1000));
    if (deltaSeconds < 2) {
        return "just now";
    }
    if (deltaSeconds < 60) {
        return `${deltaSeconds}s ago`;
    }
    const deltaMinutes = Math.floor(deltaSeconds / 60);
    if (deltaMinutes < 60) {
        return `${deltaMinutes}m ago`;
    }
    const deltaHours = Math.floor(deltaMinutes / 60);
    return `${deltaHours}h ago`;
}

function setStateClass(state) {
    statusDot.classList.remove("connected", "connecting", "disconnected");
    statusDot.classList.add(state);
}

function renderStatus(status) {
    serverValue.textContent = status.serverUrl || "ws://127.0.0.1:8765";
    socketValue.textContent = status.socketState || "unknown";

    if (status.connected) {
        setStateClass("connected");
        statusText.textContent = "Connected";
        detailText.textContent = "Chrome is linked to the local EmploAI bridge on this machine.";
        heartbeatValue.textContent = status.lastHeartbeatAckAt
            ? `${formatRelativeTime(status.lastHeartbeatAckAt)}`
            : "waiting";
        reconnectButton.disabled = true;
        reconnectButton.textContent = "Connected";
        return;
    }

    if (status.connecting || status.reconnectScheduled) {
        setStateClass("connecting");
        statusText.textContent = "Waiting for bot";
        detailText.textContent = "The extension is loaded and retrying the local bridge. Start the bot and use /bridge on.";
        heartbeatValue.textContent = status.lastHeartbeatAckAt
            ? `${formatRelativeTime(status.lastHeartbeatAckAt)}`
            : "not yet";
        reconnectButton.disabled = false;
        reconnectButton.textContent = "Retry now";
        return;
    }

    setStateClass("disconnected");
    statusText.textContent = "Disconnected";
    detailText.textContent = status.lastSocketError
        ? `Last issue: ${status.lastSocketError}`
        : "The extension could not reach the local EmploAI bridge yet.";
    heartbeatValue.textContent = status.lastHeartbeatAckAt
        ? `${formatRelativeTime(status.lastHeartbeatAckAt)}`
        : "never";
    reconnectButton.disabled = false;
    reconnectButton.textContent = "Retry now";
}

function requestStatus(message = { type: "emploai_popup_status" }) {
    chrome.runtime.sendMessage(message, (response) => {
        if (chrome.runtime.lastError) {
            setStateClass("disconnected");
            statusText.textContent = "Unavailable";
            detailText.textContent = chrome.runtime.lastError.message;
            socketValue.textContent = "error";
            heartbeatValue.textContent = "unknown";
            reconnectButton.disabled = false;
            reconnectButton.textContent = "Retry now";
            return;
        }
        renderStatus(response || {});
    });
}

reconnectButton.addEventListener("click", () => {
    reconnectButton.disabled = true;
    reconnectButton.textContent = "Retrying...";
    requestStatus({ type: "emploai_popup_reconnect" });
});

requestStatus();
window.setInterval(requestStatus, 1000);
