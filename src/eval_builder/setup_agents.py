"""`eval-builder setup`: register the MCP server with Claude Code, Codex and Cursor.

Shows every change first. Applies only with --yes. Backs up any file it edits.
Running it twice changes nothing the second time.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tomllib
from dataclasses import dataclass, field
from datetime import datetime
from importlib import resources
from pathlib import Path
from typing import Any

NAME = "eval-builder"
DEFAULT_SERVER = ["uvx", NAME, "mcp"]


@dataclass
class Action:
    agent: str
    kind: str  # "command" | "edit" | "copy" | "skip"
    target: str
    detail: str
    apply_fn: Any = field(default=None, repr=False)

    def as_dict(self) -> dict[str, str]:
        return {
            "agent": self.agent,
            "kind": self.kind,
            "target": self.target,
            "detail": self.detail,
        }


def skill_text() -> str:
    try:
        return resources.files("eval_builder").joinpath("data/SKILL.md").read_text("utf-8")
    except (FileNotFoundError, ModuleNotFoundError):
        repo = Path(__file__).resolve().parents[2] / "skills" / NAME / "SKILL.md"
        return repo.read_text("utf-8")


def _backup(path: Path) -> Path | None:
    if not path.exists():
        return None
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    dest = path.with_name(f"{path.name}.bak-{NAME}-{stamp}")
    shutil.copy2(path, dest)
    return dest


def _claude_action(server: list[str], path_env: str | None) -> Action:
    exe = shutil.which("claude", path=path_env)
    if not exe:
        return Action(
            "Claude Code",
            "skip",
            "claude CLI",
            "claude CLI not found on PATH; to add later run: claude mcp add --scope "
            f"user {NAME} -- {' '.join(server)}",
        )
    probe = subprocess.run([exe, "mcp", "get", NAME], capture_output=True, text=True, timeout=60)
    if probe.returncode == 0:
        return Action("Claude Code", "skip", "claude mcp", f"{NAME} already registered")
    argv = [exe, "mcp", "add", "--scope", "user", NAME, "--", *server]

    def run() -> str:
        res = subprocess.run(argv, capture_output=True, text=True, timeout=60)
        if res.returncode != 0:
            raise RuntimeError(res.stderr.strip() or res.stdout.strip())
        return res.stdout.strip()

    return Action("Claude Code", "command", "claude mcp", "run: claude " + " ".join(argv[1:]), run)


def _codex_action(home: Path, server: list[str], path_env: str | None) -> Action:
    codex_dir = home / ".codex"
    if not codex_dir.exists() and not shutil.which("codex", path=path_env):
        return Action("Codex", "skip", str(codex_dir), "Codex not detected")
    cfg = codex_dir / "config.toml"
    existing = cfg.read_text("utf-8") if cfg.exists() else ""
    try:
        parsed = tomllib.loads(existing) if existing else {}
    except tomllib.TOMLDecodeError as e:
        return Action(
            "Codex", "skip", str(cfg), f"config.toml does not parse ({e}); not touching it"
        )
    if NAME in (parsed.get("mcp_servers") or {}):
        return Action("Codex", "skip", str(cfg), f"[mcp_servers.{NAME}] already present")
    block = f'\n[mcp_servers.{NAME}]\ncommand = "{server[0]}"\nargs = {json.dumps(server[1:])}\n'

    def run() -> str:
        codex_dir.mkdir(parents=True, exist_ok=True)
        b = _backup(cfg)
        with open(cfg, "a", encoding="utf-8") as f:
            if existing and not existing.endswith("\n"):
                f.write("\n")
            f.write(block)
        return f"appended block; backup: {b}" if b else "created config.toml"

    return Action("Codex", "edit", str(cfg), f"append:{block}", run)


def _cursor_action(home: Path, server: list[str], path_env: str | None) -> Action:
    cursor_dir = home / ".cursor"
    if not cursor_dir.exists() and not shutil.which("cursor", path=path_env):
        return Action("Cursor", "skip", str(cursor_dir), "Cursor not detected")
    cfg = cursor_dir / "mcp.json"
    data: dict[str, Any] = {}
    if cfg.exists():
        try:
            data = json.loads(cfg.read_text("utf-8") or "{}")
        except json.JSONDecodeError as e:
            return Action(
                "Cursor", "skip", str(cfg), f"mcp.json does not parse ({e}); not touching it"
            )
    entry = {"command": server[0], "args": server[1:]}
    if (data.get("mcpServers") or {}).get(NAME) == entry:
        return Action("Cursor", "skip", str(cfg), f"{NAME} already present")

    def run() -> str:
        cursor_dir.mkdir(parents=True, exist_ok=True)
        b = _backup(cfg)
        data.setdefault("mcpServers", {})[NAME] = entry
        cfg.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        return f"wrote mcpServers.{NAME}; backup: {b}" if b else f"created {cfg}"

    return Action("Cursor", "edit", str(cfg), f"set mcpServers.{NAME} = {json.dumps(entry)}", run)


def _skill_actions(home: Path) -> list[Action]:
    text = skill_text()
    out = []
    for agent, base in (("Claude Code", home / ".claude"), ("Codex", home / ".codex")):
        dest = base / "skills" / NAME / "SKILL.md"
        if not base.exists():
            out.append(Action(agent, "skip", str(dest), f"{base} not found"))
            continue
        if dest.exists() and dest.read_text("utf-8") == text:
            out.append(Action(agent, "skip", str(dest), "skill already up to date"))
            continue

        def run(dest: Path = dest) -> str:
            dest.parent.mkdir(parents=True, exist_ok=True)
            b = _backup(dest)
            dest.write_text(text, encoding="utf-8")
            return f"wrote skill; backup: {b}" if b else "wrote skill"

        out.append(Action(agent, "copy", str(dest), "install agent instructions (SKILL.md)", run))
    return out


def plan(
    home: Path | None = None, server: list[str] | None = None, path_env: str | None = None
) -> list[Action]:
    home = home or Path.home()
    server = server or DEFAULT_SERVER
    return [
        _claude_action(server, path_env),
        _codex_action(home, server, path_env),
        _cursor_action(home, server, path_env),
        *_skill_actions(home),
    ]


def setup(
    yes: bool = False,
    home: Path | None = None,
    server: list[str] | None = None,
    path_env: str | None = None,
) -> dict[str, Any]:
    actions = plan(home, server, path_env)
    result: dict[str, Any] = {"applied": False, "actions": [a.as_dict() for a in actions]}
    if not yes:
        result["next"] = "re-run with --yes to apply the changes above"
        return result
    for a, d in zip(actions, result["actions"], strict=True):
        if a.apply_fn is None:
            continue
        try:
            d["result"] = a.apply_fn()
        except Exception as e:  # report and continue with the other agents
            d["result"] = f"failed: {e}"
    result["applied"] = True
    return result
