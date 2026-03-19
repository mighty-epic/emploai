import single_agent.agent as single_agent_module
from single_agent.agent import SingleAgent


class FakePyAutoGUI:
    def __init__(self):
        self.moves = []
        self.clicks = 0

    def moveTo(self, x, y, duration=0.1):
        self.moves.append((x, y, duration))

    def click(self):
        self.clicks += 1


def test_single_agent_click_tolerates_comma_polluted_coordinates(monkeypatch, tmp_path):
    fake_pyautogui = FakePyAutoGUI()
    monkeypatch.setattr(single_agent_module, "PYAUTOGUI_AVAILABLE", True)
    monkeypatch.setattr(single_agent_module, "pyautogui", fake_pyautogui)

    agent = SingleAgent(screenshot_dir=str(tmp_path))

    result = agent._click("1467, 25", "25")

    assert result["success"] is True
    assert fake_pyautogui.moves == [(1467, 25, 0.1)]
    assert fake_pyautogui.clicks == 1
