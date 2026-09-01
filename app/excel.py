"""Excel (.xlsx) import/export for test cases — the only supported bulk format.

Columns map 1:1 to the professional test-case fields. `steps` is flattened into a
single multi-line cell (``action => expected`` per line) and parsed back on import.
"""

from __future__ import annotations

import io
from typing import Any

from openpyxl import Workbook, load_workbook

# (header, field key) in column order
COLUMNS: list[tuple[str, str]] = [
    ("Case Key", "case_key"),
    ("Module", "module"),
    ("Name", "name"),
    ("Priority", "priority"),
    ("Type", "type"),
    ("Status", "status"),
    ("Owner", "owner"),
    ("Tags", "tags"),
    ("References", "references"),
    ("Preconditions", "preconditions"),
    ("Agent Task (prompt)", "prompt"),
    ("Steps", "steps"),
    ("Test Data", "test_data"),
    ("Expected", "expected"),
    ("Start URL", "start_url"),
    ("Enabled", "enabled"),
]

_TRUE = {"1", "true", "yes", "y", "是", "启用", "enabled"}


def _steps_to_cell(steps: list[dict]) -> str:
    lines = []
    for st in steps or []:
        action = (st.get("action") or "").strip()
        expected = (st.get("expected") or "").strip()
        lines.append(f"{action} => {expected}" if expected else action)
    return "\n".join(lines)


def _cell_to_steps(text: str) -> list[dict]:
    steps = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        action, sep, expected = line.partition("=>")
        steps.append({"action": action.strip(), "expected": expected.strip() if sep else ""})
    return steps


def _tags_to_cell(tags: list[str]) -> str:
    return ", ".join(tags or [])


def _cell_to_tags(text: str) -> list[str]:
    return [t.strip() for t in (text or "").split(",") if t.strip()]


def build_workbook(cases: list[dict]) -> bytes:
    """Serialize case dicts (as returned by the API) to .xlsx bytes."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Test Cases"
    ws.append([h for h, _ in COLUMNS])
    for c in cases:
        row = []
        for _, key in COLUMNS:
            if key == "steps":
                row.append(_steps_to_cell(c.get("steps", [])))
            elif key == "tags":
                row.append(_tags_to_cell(c.get("tags", [])))
            elif key == "enabled":
                row.append("是" if c.get("enabled", True) else "否")
            else:
                row.append(c.get(key) or "")
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def template_bytes() -> bytes:
    """A header-only workbook with one example row to guide users."""
    example = {
        "case_key": "",
        "module": "采购/询价",
        "name": "询价单列表查询",
        "priority": "P1",
        "type": "smoke",
        "status": "active",
        "owner": "",
        "tags": ["询价", "只读"],
        "references": "REQ-000001",
        "preconditions": "已登录采购系统",
        "prompt": "打开询价单列表页面，确认至少有一条记录并能看到询价单号列。",
        "steps": [{"action": "打开询价单列表", "expected": "列表加载成功"}],
        "test_data": "",
        "expected": "列表中至少一条询价单记录",
        "start_url": "",
        "enabled": True,
    }
    return build_workbook([example])


def parse_workbook(data: bytes) -> list[dict[str, Any]]:
    """Read .xlsx bytes into TestCaseIn-compatible dicts (header-matched, order-agnostic)."""
    wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    ws = wb.active
    rows = ws.iter_rows(values_only=True)
    headers = [str(h).strip() if h is not None else "" for h in next(rows, [])]
    header_to_key = {h: k for h, k in COLUMNS}
    idx = {i: header_to_key.get(h) for i, h in enumerate(headers)}

    out: list[dict[str, Any]] = []
    for raw in rows:
        rec: dict[str, Any] = {}
        for i, val in enumerate(raw):
            key = idx.get(i)
            if not key:
                continue
            text = "" if val is None else str(val).strip()
            if key == "steps":
                rec[key] = _cell_to_steps(text)
            elif key == "tags":
                rec[key] = _cell_to_tags(text)
            elif key == "enabled":
                rec[key] = text.lower() in _TRUE if text else True
            elif key in ("case_key", "module", "owner", "start_url"):
                rec[key] = text or None
            else:
                rec[key] = text
        if rec.get("name") and rec.get("prompt"):  # skip blank/incomplete rows
            out.append(rec)
    return out
