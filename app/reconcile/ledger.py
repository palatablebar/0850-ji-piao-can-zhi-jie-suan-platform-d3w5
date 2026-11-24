from decimal import Decimal

from app.catalog import SPEC
from app.reconcile.checks import all_checks


def build_ledger(intake, prepared, prepare_issues, results, signing=None):
    counts = dict(intake["counts"])
    counts["prepared"] = len(prepared)
    counts["prepare_issues"] = len(prepare_issues)
    counts["computed"] = len(results)
    balanced = counts["input"] == counts["accepted"] + counts["isolated"] + counts["duplicates"] + counts["ignored"]
    metric = sum((item.get("metric") for item in results if item.get("metric") is not None), Decimal("0"))

    net_values = {item["net_cents"] for item in prepared}
    net_total = next(iter(net_values)) if len(net_values) == 1 else None
    net_feasible = bool(results) and all(item.get("net_feasible") for item in results)
    # 已确定应结金额的票，其有符号应结之和必须等于团单净额（凭据票+唯一分解票）
    determined = [item for item in results if item.get("due_cents") is not None]
    due_sum = sum(item["due_cents"] for item in determined)
    net_consistent = net_feasible and all(
        item.get("contribution_low") == item.get("contribution_high") for item in results
    ) and due_sum == net_total

    checks = [
        {"id": "source", "label": "来源行守恒", "ok": balanced},
        {"id": "computed", "label": "计算条目完整", "ok": counts["computed"] == len(results)},
        {"id": "net", "label": "净额方向与上限配平", "ok": net_feasible},
        {"id": "due", "label": "应结金额与净额一致", "ok": net_consistent},
    ]
    if signing is not None:
        signed_sum = signing["totals"]["signed_total_cents"]
        expected = sum(s["due_cents"] for s in signing["tickets"] if s["sign_state"] == "SIGNED")
        checks.append({"id": "signing", "label": "签发款不新增实收实退", "ok": signed_sum == expected})
    return {"counts": counts, "balanced": balanced, "metric_field": SPEC.get("metric_field", "metric"),
            "net_total_cents": net_total,
            "metric_total": str(metric), "checks": checks, "all_checks": all_checks(checks)}
