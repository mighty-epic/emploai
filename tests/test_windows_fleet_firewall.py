from __future__ import annotations

from pathlib import Path

from shared.windows_fleet_firewall import (
    FIREWALL_RULE_PREFIX,
    _inspection_script,
    _repair_script,
    firewall_configuration_required,
)


ROOT = Path(__file__).resolve().parents[1]


def test_firewall_configuration_required_only_for_enabled_unconfigured_windows_firewall():
    assert firewall_configuration_required({"applicable": True, "firewallEnabled": True, "configured": False}) is True
    assert firewall_configuration_required({"applicable": True, "firewallEnabled": True, "configured": True}) is False
    assert firewall_configuration_required({"applicable": True, "firewallEnabled": False, "configured": False}) is False
    assert firewall_configuration_required({"applicable": False, "firewallEnabled": True, "configured": False}) is False


def test_firewall_scripts_are_scoped_to_runtime_port_program_and_yggdrasil_network(tmp_path):
    program = Path(r"C:\Program Files\Python313\python.exe")
    inspection = _inspection_script(port=8787, program=program)
    repair = _repair_script(port=8787, program=program, result_path=tmp_path / "result.json")

    assert str(program).replace("'", "''") in inspection
    assert "$Port = 8787" in inspection
    assert "200::/7" in inspection
    assert "broadAllowRuleNames" in inspection
    assert "externalBroadAllowRuleNames" in inspection
    assert "externalBlockRuleNames" in inspection
    assert "Test-BroadAddress" in inspection
    assert "DisplayName -like 'EmploAI*'" in inspection
    assert "-LocalPort $Port" in repair
    assert "-RemoteAddress '200::/7'" in repair
    assert "-Program $Program" in repair
    assert "-InterfaceAlias 'Yggdrasil'" in repair
    assert "Disable-NetFirewallRule" in repair
    assert "Test-BroadAddress" in repair
    assert "$EmploAIRule -and $ProgramMatches" in repair
    assert "EmploAI will not disable unrelated firewall rules" in (ROOT / "shared" / "windows_fleet_firewall.py").read_text(encoding="utf-8")
    assert f'{FIREWALL_RULE_PREFIX} 8787' in repair
