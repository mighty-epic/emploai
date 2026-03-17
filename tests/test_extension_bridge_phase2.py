from single_agent.extension_tool import ExtensionTool


def test_extension_tool_clear_ref_surfaces_verified_field_value():
    tool = ExtensionTool()

    states = [
        {
            "tab_id": 101,
            "window_id": 1,
            "url": "https://example.com/form",
            "title": "Form",
            "snapshot_hash": "before",
            "interactive_count": 2,
            "focused_ref": 7,
        },
        {
            "tab_id": 101,
            "window_id": 1,
            "url": "https://example.com/form",
            "title": "Form",
            "snapshot_hash": "after",
            "interactive_count": 2,
            "focused_ref": 7,
        },
    ]

    def fake_get_state(_tab_id=None):
        return states.pop(0)

    def fake_command(action, params=None, timeout=30):
        assert action == "clear_ref"
        assert params == {"ref": 7, "tabId": 101}
        return {"success": True, "result": {"fieldValue": "", "cleared": True}}

    tool._get_state = fake_get_state
    tool._command = fake_command

    result = tool.clear_ref(7, tab_id=101)

    assert result["success"] is True
    assert result["wait_reason"] == "field_cleared"
    assert result["field_value"] == ""
    assert result["cleared"] is True


def test_extension_tool_select_option_surfaces_selected_metadata():
    tool = ExtensionTool()

    states = [
        {
            "tab_id": 101,
            "window_id": 1,
            "url": "https://example.com/form",
            "title": "Form",
            "snapshot_hash": "before",
            "interactive_count": 3,
            "focused_ref": 5,
        },
        {
            "tab_id": 101,
            "window_id": 1,
            "url": "https://example.com/form",
            "title": "Form",
            "snapshot_hash": "after",
            "interactive_count": 3,
            "focused_ref": 5,
        },
    ]

    def fake_get_state(_tab_id=None):
        return states.pop(0)

    def fake_command(action, params=None, timeout=30):
        assert action == "select_option_ref"
        assert params == {"ref": 5, "tabId": 101, "text": "Canada"}
        return {"success": True, "result": {"selectedText": "Canada", "selectedValue": "ca"}}

    tool._get_state = fake_get_state
    tool._command = fake_command

    result = tool.select_option_by_ref(5, text="Canada", tab_id=101)

    assert result["success"] is True
    assert result["wait_reason"] == "option_selected"
    assert result["selected_text"] == "Canada"
    assert result["selected_value"] == "ca"


def test_extension_tool_wait_for_matches_text_condition():
    tool = ExtensionTool()

    def fake_get_state(_tab_id=None):
        return {
            "tab_id": 101,
            "window_id": 1,
            "url": "https://example.com/progress",
            "title": "Processing",
            "snapshot_hash": "same",
            "interactive_count": 1,
            "focused_ref": None,
        }

    text_responses = iter([
        {"text": "Still working"},
        {"text": "Finished successfully"},
    ])

    tool._get_state = fake_get_state
    tool._get_page_text = lambda _tab_id=None: next(text_responses)

    result = tool.wait_for(text_contains="successfully", timeout_seconds=1, tab_id=101)

    assert result["success"] is True
    assert result["wait_reason"] == "wait_condition_met"
    assert result["matched_conditions"] == ["text_contains"]
