from __future__ import annotations

import json
import stat
import tomllib
from pathlib import Path

from eval_builder.setup_agents import setup


def _fake_claude(bin_dir: Path, log: Path, registered: bool = False) -> None:
    bin_dir.mkdir(parents=True, exist_ok=True)
    exe = bin_dir / "claude"
    exe.write_text(
        "#!/bin/sh\n"
        f'echo "$@" >> "{log}"\n'
        f'if [ "$2" = "get" ]; then exit {0 if registered else 1}; fi\n'
        "exit 0\n"
    )
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)


def test_dry_run_changes_nothing(tmp_path: Path) -> None:
    home = tmp_path / "home"
    (home / ".codex").mkdir(parents=True)
    r = setup(yes=False, home=home, path_env=str(tmp_path / "empty"))
    assert r["applied"] is False
    kinds = {(a["agent"], a["kind"]) for a in r["actions"]}
    assert ("Claude Code", "skip") in kinds and ("Codex", "edit") in kinds
    assert not (home / ".codex" / "config.toml").exists()


def test_apply_backup_and_idempotent(tmp_path: Path) -> None:
    home = tmp_path / "home"
    (home / ".codex").mkdir(parents=True)
    (home / ".cursor").mkdir()
    (home / ".claude").mkdir()
    (home / ".codex" / "config.toml").write_text('model = "o3"\n')
    (home / ".cursor" / "mcp.json").write_text(json.dumps({"mcpServers": {"other": {}}}))
    log = tmp_path / "claude.log"
    _fake_claude(tmp_path / "bin", log)
    path_env = str(tmp_path / "bin")

    r = setup(yes=True, home=home, path_env=path_env)
    assert r["applied"]
    cfg = tomllib.loads((home / ".codex" / "config.toml").read_text())
    assert cfg["model"] == "o3"
    assert cfg["mcp_servers"]["eval-builder"] == {"command": "uvx", "args": ["eval-builder", "mcp"]}
    cur = json.loads((home / ".cursor" / "mcp.json").read_text())
    assert cur["mcpServers"]["eval-builder"]["args"] == ["eval-builder", "mcp"]
    assert "other" in cur["mcpServers"]
    assert (home / ".claude" / "skills" / "eval-builder" / "SKILL.md").exists()
    assert (home / ".codex" / "skills" / "eval-builder" / "SKILL.md").exists()
    backups = list((home / ".codex").glob("config.toml.bak-eval-builder-*"))
    assert len(backups) == 1 and backups[0].read_text() == 'model = "o3"\n'
    assert "mcp add --scope user eval-builder -- uvx eval-builder mcp" in log.read_text()

    # second run: everything is already in place
    _fake_claude(tmp_path / "bin", log, registered=True)
    r2 = setup(yes=True, home=home, path_env=path_env)
    assert all(a["kind"] == "skip" for a in r2["actions"]), r2["actions"]
    assert (home / ".codex" / "config.toml").read_text().count("[mcp_servers.eval-builder]") == 1


def test_default_home_is_the_temp_home(tmp_path: Path) -> None:
    # conftest points HOME at a temp dir for every test, so setup() without home= is safe
    assert Path.home() != Path("/Users") and "pytest" in str(Path.home())


def test_codex_on_path_without_config_dir_is_set_up_in_one_run(tmp_path: Path) -> None:
    # Codex installed but never run: ~/.codex does not exist yet
    home = tmp_path / "home"
    home.mkdir()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    codex = bin_dir / "codex"
    codex.write_text("#!/bin/sh\nexit 0\n")
    codex.chmod(codex.stat().st_mode | stat.S_IEXEC)
    r = setup(yes=True, home=home, path_env=str(bin_dir))
    assert (home / ".codex" / "config.toml").exists()
    assert (home / ".codex" / "skills" / "eval-builder" / "SKILL.md").exists()
    assert "restart" in r["next"]
    r2 = setup(yes=True, home=home, path_env=str(bin_dir))
    codex_actions = [a for a in r2["actions"] if a["agent"] == "Codex"]
    assert all(a["kind"] == "skip" for a in codex_actions), codex_actions
