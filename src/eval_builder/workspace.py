"""Standard file layout inside a workspace directory. Every step reads and writes here."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Workspace:
    root: Path

    @classmethod
    def at(cls, path: str | Path) -> Workspace:
        return cls(Path(path))

    def ensure(self) -> Workspace:
        self.root.mkdir(parents=True, exist_ok=True)
        return self

    @property
    def traces(self) -> Path:
        return self.root / "traces.jsonl"

    @property
    def ingest_report(self) -> Path:
        return self.root / "ingest.json"

    @property
    def selection(self) -> Path:
        return self.root / "selection.json"

    @property
    def cases(self) -> Path:
        return self.root / "cases.yaml"

    @property
    def rubric(self) -> Path:
        return self.root / "rubric.yaml"

    @property
    def judge_requests(self) -> Path:
        return self.root / "judge_requests.jsonl"

    @property
    def judgments(self) -> Path:
        return self.root / "judgments.jsonl"

    @property
    def labels(self) -> Path:
        return self.root / "labels.jsonl"

    @property
    def label_sheet_html(self) -> Path:
        return self.root / "label_sheet.html"

    @property
    def label_sheet_csv(self) -> Path:
        return self.root / "label_sheet.csv"

    @property
    def label_plan(self) -> Path:
        return self.root / "label_plan.json"

    @property
    def judge_check(self) -> Path:
        return self.root / "judge_check.json"

    @property
    def exports(self) -> Path:
        return self.root / "exports"

    @property
    def report_md(self) -> Path:
        return self.root / "report.md"

    @property
    def report_json(self) -> Path:
        return self.root / "report.json"
