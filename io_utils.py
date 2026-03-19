from __future__ import annotations

from ast import literal_eval
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Iterable, Mapping, Optional, Tuple

import pandas as pd


Point = Tuple[int, int]


def parse_point_text(value: str) -> Optional[Point]:
    """Parse point text like '(123, 456)' safely.

    Returns None when the input cannot be parsed into a 2-item numeric tuple.
    """
    try:
        parsed = literal_eval(value)
    except (SyntaxError, ValueError):
        return None

    if not isinstance(parsed, tuple) or len(parsed) != 2:
        return None

    x, y = parsed
    if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
        return None

    return int(x), int(y)


def records_checksum(records: Iterable[Mapping[str, Any]]) -> int:
    """Build a stable hash for change detection before autosave."""
    normalized = []
    for record in records:
        normalized.append(tuple(sorted(record.items())))
    return hash(tuple(normalized))


def save_records_to_csv(records: list[Mapping[str, Any]], outpath: Path) -> None:
    """Write records to CSV atomically to avoid partial/corrupted output files."""
    outpath.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame.from_records(records)

    with NamedTemporaryFile("w", suffix=".csv", dir=str(outpath.parent), delete=False, newline="") as tmp_file:
        tmp_path = Path(tmp_file.name)
        df.to_csv(tmp_file.name, index=False)

    tmp_path.replace(outpath)
