from datetime import date

from app.domain.helpers import D


def _today():
    # 单一可替换入口，便于测试固定业务日期
    return date.today()


def decide_rows(items, today=None):
    today = today or _today()
    for item in items:
        item["same_day"] = item.get("issue_date") == today
        if item.get("group_issue"):
            item["verdict"] = "REJECT"
            item["reason"] = item["group_issue"]
        elif not item.get("net_feasible", False):
            item["verdict"] = "REJECT"
            item["reason"] = "NET_UNBALANCED"
        elif item["basis"] == "EVIDENCE":
            item["verdict"] = "PASS"
            item["reason"] = "EVIDENCE_APPROVED"
        elif item["basis"] == "NET_UNIQUE":
            item["verdict"] = "PASS"
            item["reason"] = "NET_SPLIT_UNIQUE"
        else:
            item["verdict"] = "REVIEW"
            item["reason"] = "NET_SPLIT_AMBIGUOUS"

        # 能对账的票款要当天签发：非当天票不能进入当天签发，转人工复核
        if item["verdict"] == "PASS" and not item["same_day"]:
            item["verdict"] = "REVIEW"
            item["reason"] = "NOT_SAME_DAY"
        item.setdefault("verdict", "REVIEW")
        item.setdefault("reason", "OK")
        # 统一指标类型，便于对账层求和
        item["metric"] = D(str(item["metric"]), "CALC") if item.get("metric") is not None else None
    return items
