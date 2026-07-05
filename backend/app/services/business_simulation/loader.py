"""Load JSON/YAML simulation inputs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml


def load_structured_file(path: str | Path) -> dict[str, Any]:
    file_path = Path(path)
    with file_path.open("r", encoding="utf-8") as handle:
        if file_path.suffix.lower() in {".yaml", ".yml"}:
            data = yaml.safe_load(handle) or {}
        else:
            data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Expected mapping in {file_path}")
    return data


def write_json(path: str | Path, data: Any) -> None:
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with file_path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
