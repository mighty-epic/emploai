from pathlib import Path


def test_popup_html_loads_popup_script_and_live_fields():
    repo_root = Path(__file__).resolve().parents[1]
    popup_html = (repo_root / "browser_extension" / "popup.html").read_text(encoding="utf-8")

    assert '<script src="popup.js"></script>' in popup_html
    assert 'id="server-value"' in popup_html
    assert 'id="socket-value"' in popup_html
    assert 'id="heartbeat-value"' in popup_html
    assert 'id="reconnect-button"' in popup_html


def test_background_js_exposes_popup_bridge_status_api():
    repo_root = Path(__file__).resolve().parents[1]
    background_js = (repo_root / "browser_extension" / "background.js").read_text(encoding="utf-8")
    popup_js = (repo_root / "browser_extension" / "popup.js").read_text(encoding="utf-8")

    assert "function getBridgeStatus()" in background_js
    assert 'message?.type === "emploai_popup_status"' in background_js
    assert 'message?.type === "emploai_popup_reconnect"' in background_js
    assert "lastHeartbeatAckAt" in background_js
    assert "socketState" in background_js
    assert 'chrome.runtime.sendMessage(message, (response) => {' in popup_js
    assert 'type: "emploai_popup_status"' in popup_js
    assert 'type: "emploai_popup_reconnect"' in popup_js
