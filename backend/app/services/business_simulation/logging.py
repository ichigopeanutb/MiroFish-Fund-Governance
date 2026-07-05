"""Append-only JSONL writers for business simulation outputs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel


class JsonlWriter:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("", encoding="utf-8")

    def write(self, item: BaseModel | dict[str, Any]) -> None:
        if isinstance(item, BaseModel):
            payload = item.model_dump(mode="json")
        else:
            payload = item
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
