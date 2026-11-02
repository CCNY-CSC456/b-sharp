from functools import cache
from pathlib import Path

from enum import StrEnum


@cache
def load_queries(filename: str = "queries.sql") -> StrEnum:
    """Load a named SQL file from the central sql/ directory."""
    # Path(__file__) is src/tower/messaging/query_loader.py
    # .parent.parent moves up to src/tower/
    path = Path(__file__).parent.parent / "sql" / filename
    content = path.read_text(encoding="utf-8")

    queries = {}
    current_name = None
    current_lines = []

    for line in content.splitlines():
        if line.strip().startswith("-- name:"):
            if current_name:
                queries[current_name] = "\n".join(current_lines).strip()
                current_lines = []
            current_name = line.replace("-- name:", "").strip()
        elif current_name:
            current_lines.append(line)

    if current_name:
        queries[current_name] = "\n".join(current_lines).strip()

    return StrEnum("Queries", queries)


def load_schema(filename: str) -> str:
  schema_path = Path(__file__).parent.parent/ "sql" / filename
  return schema_path.read_text(encoding="utf-8")