from __future__ import annotations

import shlex


def classify_shell_command(command: str) -> str:
    parts = shlex.split(command)
    if not parts:
        return "reject"
    lowered = command.lower()
    if "|" in command and any(fetcher in parts[0] for fetcher in ("curl", "wget")):
        if any(shell_name in lowered for shell_name in ("| sh", "| bash", "| zsh", "| python")):
            return "reject"
    if parts[0] in {"python", "python3"}:
        if len(parts) == 3 and parts[1] == "-c" and _is_low_risk_python_snippet(parts[2]):
            return "allow"
        return "confirm"
    return "confirm"


def _is_low_risk_python_snippet(code: str) -> bool:
    stripped = code.strip()
    if not (stripped.startswith("print(") and stripped.endswith(")")):
        return False
    return all(token not in stripped for token in (";", "import", "__", "open(", "exec(", "eval("))
