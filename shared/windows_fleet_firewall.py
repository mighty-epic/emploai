from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from shared.subprocess_utils import hidden_subprocess_kwargs


YGGDRASIL_REMOTE_PREFIX = "200::/7"
FIREWALL_RULE_PREFIX = "EmploAI Yggdrasil Fleet"


def _powershell_literal(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _firewall_filter_functions() -> str:
    return r"""
function Test-PortApplies($Rule, [int]$Port) {
  foreach ($Filter in @($Rule | Get-NetFirewallPortFilter -ErrorAction SilentlyContinue)) {
    $Protocol = [string]$Filter.Protocol
    $LocalPort = [string]$Filter.LocalPort
    if (($Protocol -in @('TCP', '6', 'Any', '256')) -and ($LocalPort -eq 'Any' -or $LocalPort -eq [string]$Port)) {
      return $true
    }
  }
  return $false
}

function Get-RuleProgram($Rule) {
  $Filter = $Rule | Get-NetFirewallApplicationFilter -ErrorAction SilentlyContinue | Select-Object -First 1
  return [string]$Filter.Program
}

function Test-AllowAddress($Rule) {
  foreach ($Filter in @($Rule | Get-NetFirewallAddressFilter -ErrorAction SilentlyContinue)) {
    foreach ($RemoteAddress in @($Filter.RemoteAddress)) {
      if ([string]$RemoteAddress -in @('Any', '200::/7')) {
        return $true
      }
    }
  }
  return $false
}
"""


def _inspection_script(*, port: int, program: Path) -> str:
    return f"""
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$Program = {_powershell_literal(str(program))}
$Port = {int(port)}
{_firewall_filter_functions()}
$EnabledProfiles = @(Get-NetFirewallProfile -PolicyStore ActiveStore | Where-Object Enabled)
$InboundRules = @(Get-NetFirewallRule -PolicyStore ActiveStore -Enabled True -Direction Inbound -ErrorAction Stop | Where-Object {{ $_.PrimaryStatus -ne 'Inactive' }})
$BlockNames = @(
  foreach ($Rule in @($InboundRules | Where-Object Action -eq 'Block')) {{
    $RuleProgram = Get-RuleProgram $Rule
    if ($RuleProgram -and $RuleProgram -ne 'Any' -and $RuleProgram -ieq $Program -and (Test-PortApplies $Rule $Port)) {{
      [string]$Rule.Name
    }}
  }}
)
$AllowNames = @(
  foreach ($Rule in @($InboundRules | Where-Object Action -eq 'Allow')) {{
    $RuleProgram = Get-RuleProgram $Rule
    $ProgramMatches = ($RuleProgram -ieq $Program) -or (($RuleProgram -eq 'Any' -or -not $RuleProgram) -and ([string]$Rule.DisplayName -like 'EmploAI*'))
    if ($ProgramMatches -and (Test-PortApplies $Rule $Port) -and (Test-AllowAddress $Rule)) {{
      [string]$Rule.Name
    }}
  }}
)
[pscustomobject]@{{
  applicable = $true
  firewallEnabled = ($EnabledProfiles.Count -gt 0)
  configured = (($EnabledProfiles.Count -eq 0) -or ($BlockNames.Count -eq 0 -and $AllowNames.Count -gt 0))
  port = $Port
  program = $Program
  conflictingBlockRuleNames = $BlockNames
  allowRuleNames = $AllowNames
}} | ConvertTo-Json -Depth 5 -Compress
"""


def _repair_script(*, port: int, program: Path, result_path: Path) -> str:
    rule_name = f"{FIREWALL_RULE_PREFIX} {int(port)}"
    return f"""
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$Program = {_powershell_literal(str(program))}
$Port = {int(port)}
$RuleName = {_powershell_literal(rule_name)}
$ResultPath = {_powershell_literal(str(result_path))}
{_firewall_filter_functions()}
try {{
  $Disabled = @()
  $BlockRules = @(Get-NetFirewallRule -PolicyStore ActiveStore -Enabled True -Direction Inbound -Action Block -ErrorAction Stop)
  foreach ($Rule in $BlockRules) {{
    $RuleProgram = Get-RuleProgram $Rule
    if ($RuleProgram -and $RuleProgram -ne 'Any' -and $RuleProgram -ieq $Program -and (Test-PortApplies $Rule $Port)) {{
      Disable-NetFirewallRule -Name $Rule.Name -ErrorAction Stop | Out-Null
      $Disabled += [string]$Rule.Name
    }}
  }}
  Get-NetFirewallRule -DisplayName $RuleName -ErrorAction SilentlyContinue | Remove-NetFirewallRule -ErrorAction Stop
  New-NetFirewallRule -DisplayName $RuleName -Direction Inbound -Action Allow -Protocol TCP -LocalPort $Port -RemoteAddress '{YGGDRASIL_REMOTE_PREFIX}' -Program $Program -Profile Any -InterfaceAlias 'Yggdrasil' -ErrorAction Stop | Out-Null
  [pscustomobject]@{{ ok = $true; disabledBlockRuleNames = $Disabled; ruleName = $RuleName }} |
    ConvertTo-Json -Depth 4 -Compress | Set-Content -LiteralPath $ResultPath -Encoding UTF8
}} catch {{
  [pscustomobject]@{{ ok = $false; error = $_.Exception.Message }} |
    ConvertTo-Json -Depth 4 -Compress | Set-Content -LiteralPath $ResultPath -Encoding UTF8
  exit 1
}}
"""


def _parse_json_output(output: str) -> dict[str, Any]:
    text = str(output or "").lstrip("\ufeff").strip()
    if not text:
        raise RuntimeError("Windows Firewall did not return a status result")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Windows Firewall returned an unreadable status result") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError("Windows Firewall returned an invalid status result")
    return parsed


def _run_powershell_json(script: str, *, timeout_seconds: float = 30.0) -> dict[str, Any]:
    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            script,
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=max(1.0, timeout_seconds),
        **hidden_subprocess_kwargs(),
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "Windows Firewall status check failed").strip()
        raise RuntimeError(detail[:2000])
    return _parse_json_output(completed.stdout)


def _run_elevated_repair(script: str, *, result_path: Path, timeout_seconds: float = 120.0) -> dict[str, Any]:
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    launcher = (
        "$ErrorActionPreference='Stop';"
        "$p=Start-Process -FilePath 'powershell.exe' -Verb RunAs -WindowStyle Hidden -Wait -PassThru "
        f"-ArgumentList @('-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-EncodedCommand','{encoded}');"
        "exit $p.ExitCode"
    )
    try:
        completed = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", launcher],
            check=False,
            capture_output=True,
            text=True,
            timeout=max(1.0, timeout_seconds),
            **hidden_subprocess_kwargs(),
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Windows Firewall approval timed out") from exc
    if not result_path.exists():
        detail = (completed.stderr or completed.stdout or "").strip()
        raise RuntimeError(
            ("Windows Firewall approval was canceled or the rule could not be configured. " + detail).strip()[:2000]
        )
    result = _parse_json_output(result_path.read_text(encoding="utf-8-sig"))
    if completed.returncode != 0 or not bool(result.get("ok")):
        raise RuntimeError(str(result.get("error") or "Windows Firewall configuration failed")[:2000])
    return result


def firewall_configuration_required(status: dict[str, Any]) -> bool:
    return bool(status.get("applicable")) and bool(status.get("firewallEnabled")) and not bool(status.get("configured"))


def ensure_windows_yggdrasil_firewall(
    *,
    port: int,
    program: Path | None = None,
) -> dict[str, Any]:
    checked_port = int(port)
    if not 1 <= checked_port <= 65535:
        raise ValueError("Fleet manager port must be between 1 and 65535")
    if os.name != "nt":
        return {"applicable": False, "configured": True, "changed": False, "port": checked_port}

    checked_program = Path(program or sys.executable).expanduser().resolve()
    status = _run_powershell_json(_inspection_script(port=checked_port, program=checked_program))
    if not firewall_configuration_required(status):
        return {**status, "changed": False}

    handle = tempfile.NamedTemporaryFile(prefix="emploai-fleet-firewall-", suffix=".json", delete=False)
    result_path = Path(handle.name)
    handle.close()
    result_path.unlink(missing_ok=True)
    try:
        repair = _run_elevated_repair(
            _repair_script(port=checked_port, program=checked_program, result_path=result_path),
            result_path=result_path,
        )
    finally:
        result_path.unlink(missing_ok=True)

    verified = _run_powershell_json(_inspection_script(port=checked_port, program=checked_program))
    if firewall_configuration_required(verified):
        raise RuntimeError(
            "Windows Firewall still blocks the Yggdrasil Fleet manager after approval. Check managed firewall policy."
        )
    return {
        **verified,
        "changed": True,
        "disabledBlockRuleNames": list(repair.get("disabledBlockRuleNames") or []),
        "ruleName": repair.get("ruleName"),
    }
