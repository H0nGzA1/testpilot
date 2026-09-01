"""Round-trip tests for the Excel test-case import/export (pure, no DB)."""

import pytest

from app import excel
from app.schemas import TestCaseIn


@pytest.mark.unit
def test_build_parse_roundtrip():
    cases = [
        {
            "case_key": "TC-001",
            "module": "采购",
            "name": "询价查询",
            "priority": "P1",
            "type": "smoke",
            "status": "active",
            "owner": "alice",
            "tags": ["询价", "只读"],
            "references": "REQ-1",
            "preconditions": "已登录",
            "prompt": "打开询价列表",
            "steps": [{"action": "打开列表", "expected": "加载成功"}],
            "test_data": "厂区A",
            "expected": "至少一条",
            "start_url": "",
            "enabled": False,
        }
    ]
    parsed = excel.parse_workbook(excel.build_workbook(cases))
    assert len(parsed) == 1
    p = parsed[0]
    assert p["name"] == "询价查询"
    assert p["priority"] == "P1"
    assert p["tags"] == ["询价", "只读"]
    assert p["enabled"] is False
    assert p["steps"] == [{"action": "打开列表", "expected": "加载成功"}]
    # a parsed row must validate as a create payload
    assert TestCaseIn(**p).case_key == "TC-001"


@pytest.mark.unit
def test_blank_and_incomplete_rows_skipped():
    # a row with no name/prompt is dropped, not imported as an empty case
    cases = [
        {"name": "", "prompt": "", "priority": "P2", "type": "functional", "status": "active"},
        {
            "name": "ok",
            "prompt": "do it",
            "priority": "P2",
            "type": "functional",
            "status": "active",
        },
    ]
    parsed = excel.parse_workbook(excel.build_workbook(cases))
    assert [p["name"] for p in parsed] == ["ok"]


@pytest.mark.unit
def test_template_is_valid_workbook():
    parsed = excel.parse_workbook(excel.template_bytes())
    assert parsed and parsed[0]["name"]
    assert TestCaseIn(**parsed[0])
