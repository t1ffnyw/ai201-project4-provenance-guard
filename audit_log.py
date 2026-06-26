import json
from pathlib import Path

_LOG_PATH = Path(__file__).parent / "data" / "audit.jsonl"


def _ensure_log_dir() -> None:
    _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def append_entry(entry: dict) -> None:
    _ensure_log_dir()
    with _LOG_PATH.open("a", encoding="utf-8") as log_file:
        log_file.write(json.dumps(entry) + "\n")


def get_log(limit: int = 50) -> list[dict]:
    if not _LOG_PATH.exists():
        return []

    with _LOG_PATH.open(encoding="utf-8") as log_file:
        entries = [json.loads(line) for line in log_file if line.strip()]

    return entries[-limit:]
