from datetime import date

from app.catalog import SPEC
from app.domain.helpers import D, DAY, I, optional
from app.intake.normalize import canonical


PARSERS = {
    "money": lambda value, code: I(value, code),
    "int": lambda value, code: I(value, code),
    "int_optional": lambda value, code: optional(I, value, code),
    "int_positive": lambda value, code: positive(I(value, code)),
    "date": lambda value, code: DAY(value, code),
    "date_optional": lambda value, code: optional(DAY, value, code),
}

DIRECTIONS = {"REFUND", "CHARGE"}
ACTIONS = {"REFUND", "REISSUE"}


def positive(value):
    if value <= 0:
        raise ValueError("BAD_POSITIVE")
    return value


def _typed(rows):
    typed, issues = [], []
    for raw in rows:
        item = dict(raw)
        try:
            if not canonical(item.get(SPEC["key"], "")):
                raise ValueError("KEY_MISSING")
            for field, kind in SPEC["types"].items():
                code = "INVALID_" + field.upper()
                item[field] = PARSERS[kind](item.get(field), code)
            typed.append(item)
        except ValueError as exc:
            issues.append({"line": raw.get("_line", 0), "key": raw.get(SPEC["key"], ""), "code": str(exc)})
    return typed, issues


def prepare_rows(rows):
    """整理层：类型、方向、上限与逐票凭据的边界校验，不满足前置条件的行进隔离区。"""
    typed, issues = _typed(rows)
    items = []
    for item in typed:
        try:
            if not canonical(item.get(SPEC["key"], "")):
                raise ValueError("KEY_MISSING")
            if not canonical(item.get("order_id", "")):
                raise ValueError("ORDER_MISSING")
            action = item["action"].upper()
            if action not in ACTIONS:
                raise ValueError("BAD_ACTION")
            direction = item["direction"].upper()
            if direction not in DIRECTIONS:
                raise ValueError("BAD_DIRECTION")
            if not isinstance(item["issue_date"], date):
                raise ValueError("BAD_ISSUE_DATE")
            if item["cap_cents"] < 0:
                raise ValueError("BAD_CAP")
            item["action"] = action
            item["direction"] = direction
            evidence = item["evidence_cents"]
            if evidence is not None:
                # 已核准逐票金额必须落在该票方向和上限内
                if direction == "REFUND" and evidence > 0:
                    raise ValueError("EVIDENCE_DIRECTION")
                if direction == "CHARGE" and evidence < 0:
                    raise ValueError("EVIDENCE_DIRECTION")
                if abs(evidence) > item["cap_cents"]:
                    raise ValueError("EVIDENCE_OVER_CAP")
            items.append(item)
        except ValueError as exc:
            issues.append({"line": item.get("_line", 0), "key": item.get(SPEC["key"], ""), "code": str(exc)})
    return items, issues
