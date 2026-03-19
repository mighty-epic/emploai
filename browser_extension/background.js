// background.js for EmploAI Native Bridge
let socket = null;
let reconnectTimer = null;
let heartbeatTimer = null;
const SERVER_URL = "ws://127.0.0.1:8765";
const HEARTBEAT_INTERVAL_MS = 10000;
const RECONNECT_DELAY_MS = 1000;

function clearReconnectTimer() {
    if (reconnectTimer) {
        clearTimeout(reconnectTimer);
        reconnectTimer = null;
    }
}

function scheduleReconnect() {
    if (reconnectTimer) {
        return;
    }

    reconnectTimer = setTimeout(() => {
        reconnectTimer = null;
        connect();
    }, RECONNECT_DELAY_MS);
}

function stopHeartbeat() {
    if (heartbeatTimer) {
        clearInterval(heartbeatTimer);
        heartbeatTimer = null;
    }
}

function sendHeartbeat() {
    if (!socket || socket.readyState !== WebSocket.OPEN) {
        return;
    }

    try {
        socket.send(JSON.stringify({
            type: "heartbeat",
            timestamp: Date.now()
        }));
    } catch (error) {
        // Ignore send failures here; onclose will handle reconnect.
    }
}

function startHeartbeat() {
    stopHeartbeat();
    heartbeatTimer = setInterval(sendHeartbeat, HEARTBEAT_INTERVAL_MS);
    sendHeartbeat();
}

function sendMessage(payload) {
    if (!socket || socket.readyState !== WebSocket.OPEN) {
        throw new Error("Bridge socket is not open");
    }
    socket.send(JSON.stringify(payload));
}

function waitForTabComplete(tabId, timeoutMs = 15000) {
    return new Promise((resolve) => {
        let resolved = false;
        let timeout = null;

        const finish = (tab) => {
            if (resolved) return;
            resolved = true;
            if (timeout) clearTimeout(timeout);
            chrome.tabs.onUpdated.removeListener(listener);
            resolve(tab);
        };

        chrome.tabs.get(tabId).then((tab) => {
            if (tab && tab.status === "complete") {
                finish(tab);
            }
        }).catch(() => { });

        timeout = setTimeout(async () => {
            const tab = await chrome.tabs.get(tabId);
            finish(tab);
        }, timeoutMs);

        const listener = (updatedTabId, changeInfo, tab) => {
            if (updatedTabId === tabId && changeInfo.status === "complete") {
                finish(tab);
            }
        };

        chrome.tabs.onUpdated.addListener(listener);
    });
}

function connect() {
    if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) {
        return;
    }

    stopHeartbeat();

    try {
        socket = new WebSocket(SERVER_URL);

        socket.onopen = () => {
            console.log("Connected to EmploAI Bridge Server");
            clearReconnectTimer();
            chrome.action.setBadgeText({ text: "ON" });
            chrome.action.setBadgeBackgroundColor({ color: "#22c55e" });
            startHeartbeat();
        };

        socket.onmessage = async (event) => {
            const message = JSON.parse(event.data);
            if (message.type === "ping") {
                if (socket && socket.readyState === WebSocket.OPEN) {
                    socket.send(JSON.stringify({
                        type: "pong",
                        timestamp: Date.now()
                    }));
                }
                return;
            }

            if (message.type === "heartbeat_ack") {
                return;
            }

            const command = message;
            console.log("Received command:", command);

            try {
                const result = await handleCommand(command);
                sendMessage({
                    id: command.id,
                    success: true,
                    result: result
                });
            } catch (error) {
                console.error("Command failed:", error);
                try {
                    sendMessage({
                        id: command.id,
                        success: false,
                        error: error.message
                    });
                } catch (sendError) {
                    console.error("Failed to send command error back to bridge:", sendError);
                }
            }
        };

        socket.onclose = () => {
            socket = null;
            stopHeartbeat();
            chrome.action.setBadgeText({ text: "OFF" });
            chrome.action.setBadgeBackgroundColor({ color: "#ef4444" });
            scheduleReconnect();
        };

        socket.onerror = (error) => {
            // Silently fail, onclose will retry
        };
    } catch (e) {
        scheduleReconnect();
    }
}

async function handleCommand(command) {
    const { action, params = {} } = command;

    switch (action) {
        case "navigate":
            return await navigateTab(params);
        case "snapshot":
            return await snapshotTab(params);
        case "click_ref":
            return await executeOnResolvedTab(params, clickByRef, [params.ref]);
        case "type":
            return await executeOnResolvedTab(params, typeText, [params.text, params.clearFirst, params.ref ?? null]);
        case "clear_ref":
            return await executeOnResolvedTab(params, clearRef, [params.ref]);
        case "select_option_ref":
            return await executeOnResolvedTab(params, selectOptionByRef, [params.ref, params.text ?? null, params.value ?? null, params.index ?? null]);
        case "screenshot":
            return await captureTabScreenshot(params);
        case "scroll":
            return await executeOnResolvedTab(params, scrollPage, [params.direction, params.amount]);
        case "press_key":
            return await executeOnResolvedTab(params, pressKey, [params.key]);
        case "get_text_content":
            return await executeOnResolvedTab(params, getPageTextContent);
        case "get_info":
            return await getTabInfo(params);
        case "get_state":
            return await getTabState(params);
        case "list_tabs":
            return await listTabs();
        case "activate_tab":
            return await activateTab(params);
        case "back":
            return await executeOnResolvedTab(params, navigateHistory, ["back"]);
        case "forward":
            return await executeOnResolvedTab(params, navigateHistory, ["forward"]);
        case "switch_tab":
            return await switchTab(params.index);
        case "close_tab":
            return await closeTab(params);
        default:
            throw new Error(`Unknown action: ${action}`);
    }
}

function normalizeRequestedTabId(params = {}) {
    const rawValue = params.tab_id != null ? params.tab_id : params.tabId;
    if (rawValue == null || rawValue === "") {
        return null;
    }

    const parsed = Number(rawValue);
    return Number.isNaN(parsed) ? null : parsed;
}

async function resolveTargetTab(params = {}, options = {}) {
    const requestedTabId = normalizeRequestedTabId(params);
    if (requestedTabId != null) {
        return await chrome.tabs.get(requestedTabId);
    }

    const query = options.currentWindowOnly === false
        ? { active: true, lastFocusedWindow: true }
        : { active: true, currentWindow: true };
    const [tab] = await chrome.tabs.query(query);
    if (!tab) {
        throw new Error("No active tab found");
    }
    return tab;
}

async function ensureTabFocused(tab) {
    if (!tab) {
        throw new Error("No tab available");
    }

    if (tab.windowId != null) {
        await chrome.windows.update(tab.windowId, { focused: true });
    }
    return await chrome.tabs.update(tab.id, { active: true });
}

async function waitForTabReady(tabId, timeoutMs = 15000) {
    const completedTab = await waitForTabComplete(tabId, timeoutMs);
    const deadline = Date.now() + timeoutMs;

    while (Date.now() < deadline) {
        try {
            const results = await chrome.scripting.executeScript({
                target: { tabId },
                func: () => document.readyState
            });
            const readyState = results[0] && results[0].result;
            if (readyState === "interactive" || readyState === "complete") {
                return await chrome.tabs.get(tabId);
            }
        } catch (error) {
            // The page may still be navigating or temporarily unavailable.
        }
        await new Promise((resolve) => setTimeout(resolve, 150));
    }

    return await chrome.tabs.get(completedTab.id);
}

function enrichPageResult(result, tab) {
    return {
        ...(result || {}),
        tabId: tab.id,
        windowId: tab.windowId,
        url: result && result.url ? result.url : (tab.url || null),
        title: result && result.title ? result.title : (tab.title || ""),
        index: tab.index,
        active: Boolean(tab.active),
        pinned: Boolean(tab.pinned)
    };
}

async function executeOnTab(tabId, func, args = []) {
    const tab = await chrome.tabs.get(tabId);
    const focusedTab = await ensureTabFocused(tab);
    const results = await chrome.scripting.executeScript({
        target: { tabId: focusedTab.id },
        func: func,
        args: args
    });
    return { tab: focusedTab, result: results[0].result };
}

async function executeOnResolvedTab(params, func, args = []) {
    const tab = await resolveTargetTab(params);
    const execution = await executeOnTab(tab.id, func, args);
    return enrichPageResult(execution.result, execution.tab);
}

async function navigateTab(params = {}) {
    let targetTab = null;
    const requestedTabId = normalizeRequestedTabId(params);

    if (requestedTabId != null) {
        try {
            targetTab = await chrome.tabs.get(requestedTabId);
        } catch (error) {
            targetTab = null;
        }
    }

    if (targetTab) {
        targetTab = await chrome.tabs.update(targetTab.id, { url: params.url, active: true });
    } else {
        targetTab = await chrome.tabs.create({ url: params.url, active: true });
    }

    if (targetTab.windowId != null) {
        await chrome.windows.update(targetTab.windowId, { focused: true });
    }

    const loadedTab = await waitForTabReady(targetTab.id);
    return {
        ...serializeTab(loadedTab),
        status: "complete"
    };
}

async function snapshotTab(params = {}) {
    const tab = await resolveTargetTab(params);
    const execution = await executeOnTab(tab.id, getAriaSnapshot);
    return enrichPageResult(execution.result, execution.tab);
}

async function captureTabScreenshot(params = {}) {
    const tab = await resolveTargetTab(params);
    const focusedTab = await ensureTabFocused(tab);
    const dataUrl = await chrome.tabs.captureVisibleTab(focusedTab.windowId, { format: "png" });
    return {
        ...serializeTab(focusedTab),
        image: dataUrl.split(",")[1]
    };
}

async function getTabInfo(params = {}) {
    const tab = await resolveTargetTab(params);
    return serializeTab(tab);
}

async function getTabState(params = {}) {
    const tab = await resolveTargetTab(params);
    const execution = await executeOnTab(tab.id, getPageState);
    return enrichPageResult(execution.result, execution.tab);
}

async function switchTab(index) {
    return activateTab({ index });
}

async function closeTab(params = {}) {
    const tab = await resolveTargetTab(params);
    const closedTabId = tab.id;
    const windowId = tab.windowId;

    await chrome.tabs.remove(closedTabId);

    const remainingTabs = await chrome.tabs.query({ windowId });
    const sortedTabs = remainingTabs.sort((a, b) => a.index - b.index);
    const nextTab = sortedTabs.find((candidate) => candidate.active) || sortedTabs[0] || null;

    return {
        closedTabId,
        ...(nextTab ? serializeTab(nextTab) : {
            tabId: null,
            windowId,
            url: null,
            title: null,
            index: null,
            active: false,
            pinned: false
        })
    };
}

function normalizeTabText(value) {
    return String(value || "").trim().toLowerCase();
}

function serializeTab(tab) {
    return {
        tabId: tab.id,
        index: tab.index,
        title: tab.title || "",
        url: tab.url || "",
        active: Boolean(tab.active),
        pinned: Boolean(tab.pinned),
        windowId: tab.windowId
    };
}

async function listTabs() {
    const tabs = await chrome.tabs.query({ currentWindow: true });
    const sortedTabs = tabs.sort((a, b) => a.index - b.index);
    return {
        tabs: sortedTabs.map(serializeTab),
        count: sortedTabs.length,
        activeIndex: sortedTabs.findIndex((tab) => tab.active)
    };
}

async function activateTab(params = {}) {
    const tabs = await chrome.tabs.query({ currentWindow: true });
    const sortedTabs = tabs.sort((a, b) => a.index - b.index);

    const requestedIndex = Number.isInteger(params.index) ? params.index : Number(params.index);
    const requestedTabId = params.tab_id != null ? Number(params.tab_id) :
        (params.tabId != null ? Number(params.tabId) : null);
    const titleContains = normalizeTabText(params.title_contains || params.titleContains || params.title);
    const urlContains = normalizeTabText(params.url_contains || params.urlContains || params.url);

    let target = null;

    if (Number.isInteger(requestedIndex)) {
        target = sortedTabs[requestedIndex];
        if (!target) {
            throw new Error(`Tab index ${requestedIndex} out of range`);
        }
    } else if (requestedTabId != null && !Number.isNaN(requestedTabId)) {
        target = sortedTabs.find((tab) => tab.id === requestedTabId);
        if (!target) {
            throw new Error(`Tab id ${requestedTabId} not found`);
        }
    } else {
        if (!titleContains && !urlContains) {
            throw new Error("activate_tab requires index, tab_id, title_contains, or url_contains");
        }

        const matches = sortedTabs.filter((tab) => {
            const tabTitle = normalizeTabText(tab.title);
            const tabUrl = normalizeTabText(tab.url);
            if (titleContains && !tabTitle.includes(titleContains)) {
                return false;
            }
            if (urlContains && !tabUrl.includes(urlContains)) {
                return false;
            }
            return true;
        });

        if (!matches.length) {
            throw new Error(`No tab matched title_contains="${titleContains}" url_contains="${urlContains}"`);
        }

        if (matches.length > 1) {
            const preview = matches
                .slice(0, 5)
                .map((tab) => `[${tab.index}] ${tab.title || tab.url}`)
                .join("; ");
            throw new Error(`Multiple tabs matched. Refine the request. Matches: ${preview}`);
        }

        target = matches[0];
    }

    const updatedTab = await chrome.tabs.update(target.id, { active: true });
    if (updatedTab.windowId != null) {
        await chrome.windows.update(updatedTab.windowId, { focused: true });
    }
    return serializeTab(updatedTab);
}

function hashString(text) {
    const input = String(text || "");
    let hash = 2166136261;
    for (let index = 0; index < input.length; index += 1) {
        hash ^= input.charCodeAt(index);
        hash = Math.imul(hash, 16777619) >>> 0;
    }
    return hash.toString(16).padStart(8, "0");
}

function getFocusedRef() {
    const active = document.activeElement;
    if (!active) {
        return null;
    }
    const ref = active.getAttribute("data-aria-ref");
    return ref ? Number(ref) : null;
}

function getElementValue(element) {
    if (!element) {
        return null;
    }

    if (element.tagName === "INPUT" || element.tagName === "TEXTAREA" || element.tagName === "SELECT") {
        return element.value ?? "";
    }

    if (element.isContentEditable) {
        return element.textContent ?? "";
    }

    return element.textContent ?? "";
}

// These functions will be injected into the page
function getAriaSnapshot() {
    const INTERACTIVE_ROLES = [
        'button', 'link', 'textbox', 'checkbox', 'radio', 'menuitem',
        'menuitemcheckbox', 'menuitemradio', 'option', 'tab', 'treeitem',
        'searchbox', 'spinbutton', 'switch', 'combobox', 'slider', 'input'
    ];
    const INTERACTIVE_TAGS = new Set(['BUTTON', 'A', 'INPUT', 'TEXTAREA', 'SELECT']);

    const results = [];
    let refCounter = 1;

    function isVisible(node) {
        if (!(node instanceof Element)) return false;
        const style = window.getComputedStyle(node);
        return style.display !== 'none' &&
            style.visibility !== 'hidden' &&
            style.opacity !== '0' &&
            node.offsetWidth > 0 &&
            node.offsetHeight > 0;
    }

    function getAccessibleName(node) {
        const labelledBy = (node.getAttribute('aria-labelledby') || '')
            .split(/\s+/)
            .filter(Boolean)
            .map(id => document.getElementById(id))
            .filter(Boolean)
            .map(el => el.innerText || el.textContent || '');

        const candidates = [
            node.getAttribute('aria-label'),
            labelledBy.join(' '),
            node.innerText,
            node.textContent,
            node.getAttribute('placeholder'),
            node.getAttribute('value'),
            node.getAttribute('title'),
            node.getAttribute('name'),
            node.getAttribute('alt'),
            node.id
        ];

        for (const candidate of candidates) {
            const clean = String(candidate || '').replace(/\s+/g, ' ').trim();
            if (clean) {
                return clean.substring(0, 100);
            }
        }

        return '';
    }

    function traverse(node, depth = 0) {
        if (!node || depth > 50) return;

        if (node instanceof Element) {
            const role = node.getAttribute('role') || node.tagName.toLowerCase();
            const isInteractive = INTERACTIVE_ROLES.includes(role) || INTERACTIVE_TAGS.has(node.tagName);

            if (isInteractive && isVisible(node)) {
                const cleanText = getAccessibleName(node);

                if (cleanText || INTERACTIVE_TAGS.has(node.tagName)) {
                    const ref = refCounter++;
                    node.setAttribute('data-aria-ref', ref.toString());

                    results.push({
                        ref: ref,
                        role: role,
                        name: cleanText,
                        enabled: !node.disabled,
                        checked: node.checked || false
                    });
                }
            }

            if (node.shadowRoot) {
                traverse(node.shadowRoot, depth + 1);
            }
        }

        const children = node.children || [];
        for (const child of children) {
            if (child instanceof Element || child instanceof ShadowRoot) {
                traverse(child, depth + 1);
            }
        }
    }

    traverse(document.body);

    const lines = results.map(el => `- ${el.role} "${el.name}" [ref=${el.ref}]`);
    const formatted = lines.length > 0 ? lines.join("\n") : "No interactive elements found";
    return {
        elements: results,
        formatted: formatted,
        count: results.length,
        url: window.location.href,
        title: document.title,
        focusedRef: getFocusedRef(),
        snapshotHash: hashString(formatted)
    };
}

function getPageState() {
    const snapshot = getAriaSnapshot();
    return {
        url: snapshot.url,
        title: snapshot.title,
        snapshotHash: snapshot.snapshotHash,
        interactiveCount: snapshot.count,
        focusedRef: snapshot.focusedRef
    };
}

function focusByRef(ref) {
    const selector = `[data-aria-ref='${ref}']`;
    const element = document.querySelector(selector);
    if (!element) throw new Error(`Element with ref=${ref} not found`);

    element.scrollIntoView({ block: 'center' });
    if (typeof element.focus === "function") {
        element.focus();
    }
    return element;
}

function clickByRef(ref) {
    const element = focusByRef(ref);
    element.click();
    return {
        success: true,
        clickedRef: ref,
        url: window.location.href,
        title: document.title,
        focusedRef: getFocusedRef()
    };
}

function typeText(text, clearFirst, ref) {
    const element = ref != null ? focusByRef(ref) : document.activeElement;
    if (!element) throw new Error("No focused element");

    const isInputLike = element.tagName === 'INPUT' || element.tagName === 'TEXTAREA';
    const isEditable = isInputLike || element.isContentEditable;
    if (!isEditable) {
        throw new Error("Focused element is not typable");
    }

    if (clearFirst) {
        if (isInputLike) {
            element.value = '';
        } else {
            element.textContent = '';
        }
    }

    if (isInputLike) {
        const descriptor = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(element), "value");
        const start = element.selectionStart ?? element.value.length;
        const end = element.selectionEnd ?? element.value.length;
        const nextValue = element.value.slice(0, start) + text + element.value.slice(end);
        if (descriptor && typeof descriptor.set === "function") {
            descriptor.set.call(element, nextValue);
        } else {
            element.value = nextValue;
        }
        element.dispatchEvent(new Event('input', { bubbles: true }));
        element.dispatchEvent(new Event('change', { bubbles: true }));
    } else {
        element.textContent = `${element.textContent || ""}${text}`;
        element.dispatchEvent(new Event('input', { bubbles: true }));
    }

    const fieldValue = getElementValue(element);
    return {
        success: true,
        text: text,
        fieldValue: fieldValue,
        typedVerified: fieldValue == null || String(fieldValue).includes(String(text)),
        url: window.location.href,
        title: document.title,
        focusedRef: getFocusedRef()
    };
}

function clearRef(ref) {
    const element = focusByRef(ref);
    const isInputLike = element.tagName === 'INPUT' || element.tagName === 'TEXTAREA';
    const isEditable = isInputLike || element.isContentEditable;
    if (!isEditable) {
        throw new Error(`Element with ref=${ref} is not a clearable input`);
    }

    if (isInputLike) {
        element.value = '';
    } else {
        element.textContent = '';
    }

    element.dispatchEvent(new Event('input', { bubbles: true }));
    element.dispatchEvent(new Event('change', { bubbles: true }));

    return {
        success: true,
        ref: ref,
        cleared: true,
        fieldValue: getElementValue(element),
        url: window.location.href,
        title: document.title,
        focusedRef: getFocusedRef()
    };
}

function selectOptionByRef(ref, text, value, index) {
    const element = focusByRef(ref);
    if (element.tagName !== 'SELECT') {
        throw new Error(`Element with ref=${ref} is not a <select> element`);
    }

    let selectedOption = null;
    if (text != null) {
        selectedOption = Array.from(element.options).find((option) => option.text === text);
    } else if (value != null) {
        selectedOption = Array.from(element.options).find((option) => option.value === value);
    } else if (index != null) {
        selectedOption = element.options[Number(index)] || null;
    } else {
        throw new Error("select_option_ref requires text, value, or index");
    }

    if (!selectedOption) {
        throw new Error(`No matching option found for ref=${ref}`);
    }

    element.value = selectedOption.value;
    element.dispatchEvent(new Event('input', { bubbles: true }));
    element.dispatchEvent(new Event('change', { bubbles: true }));

    return {
        success: true,
        ref: ref,
        selectedText: selectedOption.text,
        selectedValue: selectedOption.value,
        url: window.location.href,
        title: document.title,
        focusedRef: getFocusedRef()
    };
}

function getPageTextContent() {
    const text = document.body ? (document.body.innerText || '') : '';
    return {
        text: text.slice(0, 50000),
        url: window.location.href,
        title: document.title,
        focusedRef: getFocusedRef()
    };
}

function pressKey(key) {
    const target = document.activeElement || document.body;
    if (!target) throw new Error("No focused element");

    const normalized = String(key || "").toLowerCase();
    const keyMap = {
        enter: "Enter",
        tab: "Tab",
        escape: "Escape",
        esc: "Escape",
        backspace: "Backspace",
        delete: "Delete",
        arrow_up: "ArrowUp",
        arrow_down: "ArrowDown",
        arrow_left: "ArrowLeft",
        arrow_right: "ArrowRight"
    };
    const domKey = keyMap[normalized] || key;

    ["keydown", "keypress", "keyup"].forEach((type) => {
        target.dispatchEvent(new KeyboardEvent(type, {
            key: domKey,
            bubbles: true,
            cancelable: true
        }));
    });

    return { success: true, pressed: domKey };
}

function navigateHistory(direction) {
    if (direction === "back") {
        window.history.back();
    } else {
        window.history.forward();
    }

    return {
        success: true,
        url: window.location.href,
        title: document.title
    };
}

function scrollPage(direction, amount) {
    const scrollAmount = direction === "up" ? -amount : amount;
    window.scrollBy(0, scrollAmount);
    return { success: true, direction: direction };
}

// Initial connection
connect();
