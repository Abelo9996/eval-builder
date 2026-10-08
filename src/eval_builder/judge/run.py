"""Optional judge runner. OFF by default.

eval-builder never calls a model provider and ships no API keys. This module only
starts a command YOU name (for example a script that calls your local model or your
provider), sends it one JSON request per line on stdin, and reads one JSON response
per line from stdout:

    request  (stdin):  the row from judge_requests.jsonl (includes "prompt" when the
                       rubric judge has a prompt template)
    response (stdout): {"verdict": "<label>", "raw": "<optional raw text>"}

It refuses to run unless enabled with --enable-judge-plugin or the environment
variable EVAL_BUILDER_ENABLE_JUDGE_PLUGIN=1.
"""

from __future__ import annotations

import json
import os
import queue
import shlex
import subprocess
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..io import read_json, read_jsonl, write_json
from ..workspace import Workspace

ENV_FLAG = "EVAL_BUILDER_ENABLE_JUDGE_PLUGIN"


class PluginDisabled(PermissionError):
    pass


def plugin_enabled(flag: bool) -> bool:
    return flag or os.environ.get(ENV_FLAG) == "1"


class _LineProcess:
    def __init__(self, argv: list[str]) -> None:
        self.proc = subprocess.Popen(
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        self.lines: queue.Queue[str | None] = queue.Queue()
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self) -> None:
        assert self.proc.stdout is not None
        for line in self.proc.stdout:
            self.lines.put(line)
        self.lines.put(None)

    def ask(self, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        assert self.proc.stdin is not None
        self.proc.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
        self.proc.stdin.flush()
        try:
            line = self.lines.get(timeout=timeout)
        except queue.Empty as e:
            raise TimeoutError(f"no response within {timeout}s") from e
        if line is None:
            err = self.proc.stderr.read() if self.proc.stderr else ""
            raise RuntimeError(f"judge command exited: {err.strip()[-500:]}")
        return json.loads(line)

    def close(self) -> int:
        if self.proc.stdin:
            self.proc.stdin.close()
        try:
            return self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            return -9


def judge_run(
    workspace: str | Path,
    commands: dict[str, str],
    enable: bool = False,
    timeout: float = 120.0,
    resume: bool = True,
) -> dict[str, Any]:
    if not plugin_enabled(enable):
        raise PluginDisabled(
            "the judge plugin is off by default; pass --enable-judge-plugin or set "
            f"{ENV_FLAG}=1 to let eval-builder run the judge command you provide"
        )
    ws = Workspace.at(workspace)
    if not ws.judge_requests.exists():
        raise FileNotFoundError(f"{ws.judge_requests} not found; run `eval-builder judge-plan`")
    requests = list(read_jsonl(ws.judge_requests))
    done: set[str] = set()
    if resume and ws.judgments.exists():
        done = {r["request_id"] for r in read_jsonl(ws.judgments) if "request_id" in r}
    elif ws.judgments.exists():
        ws.judgments.unlink()
    log: dict[str, Any] = {"started": datetime.now(UTC).isoformat(), "judges": {}}
    with open(ws.judgments, "a", encoding="utf-8") as out:
        for jid, cmd in commands.items():
            todo = [r for r in requests if r["judge"] == jid and r["request_id"] not in done]
            entry: dict[str, Any] = {
                "command": cmd,
                "requests": len(todo),
                "ok": 0,
                "errors": 0,
                "seconds": 0.0,
            }
            log["judges"][jid] = entry
            if not todo:
                continue
            t0 = time.monotonic()
            proc = _LineProcess(shlex.split(cmd))
            try:
                for r in todo:
                    row = {k: v for k, v in r.items() if k not in ("presented", "prompt")}
                    try:
                        resp = proc.ask(r, timeout)
                        row["verdict"] = resp.get("verdict")
                        # keep extra plugin fields (raw text, token counts) as evidence
                        row.update({k: v for k, v in resp.items() if k not in row})
                        entry["ok"] += 1
                    except (TimeoutError, RuntimeError, json.JSONDecodeError) as e:
                        row["verdict"] = None
                        row["error"] = str(e)
                        entry["errors"] += 1
                        if isinstance(e, RuntimeError):
                            out.write(json.dumps(row, ensure_ascii=False) + "\n")
                            break
                    out.write(json.dumps(row, ensure_ascii=False) + "\n")
                    out.flush()
            finally:
                entry["exit_code"] = proc.close()
                entry["seconds"] = round(time.monotonic() - t0, 2)
    missing = sorted({r["judge"] for r in requests} - set(commands))
    log["finished"] = datetime.now(UTC).isoformat()
    log["judges_without_command"] = missing
    log_path = ws.root / "judge_run_log.json"
    runs = read_json(log_path).get("runs", []) if log_path.exists() else []
    write_json(log_path, {"runs": [*runs, log]})
    return log
