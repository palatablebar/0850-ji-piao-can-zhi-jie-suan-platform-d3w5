"""团单签发规则与后补凭据处理。

规则要点：
- 已核准的逐票金额可以先签；缺凭据时，只有净额在方向与上限内的所有拆法都唯一
  指向该票应结金额，才允许签。
- 后补的逐票凭据若和原净额或已签款对不上，余款暂缓签发。
- 签发单重试不新增实收实退款项（同票同金额重试保持幂等）。
"""
from app.catalog import SPEC
from app.domain.net_split import TicketClaim, split_net

PASS_STATES = {"EVIDENCE_APPROVED", "NET_SPLIT_UNIQUE"}


def build_signing(results):
    """根据逐票判定结果生成签发视图，不修改实收实退。"""
    signing = []
    for item in results:
        if item["verdict"] == "PASS" and item.get("due_cents") is not None:
            state = "SIGNED"
            signed = item["due_cents"]
        elif item["verdict"] == "REJECT":
            state = "BLOCKED"
            signed = 0
        else:
            state = "PENDING"
            signed = 0
        signing.append({
            "ticket_id": item[SPEC["key"]],
            "order_id": item["order_id"],
            "verdict": item["verdict"],
            "reason": item["reason"],
            "basis": item["basis"],
            "direction": item["direction"],
            "cap_cents": item["cap_cents"],
            "due_cents": item.get("due_cents"),
            "signed_cents": signed,
            "sign_state": state,
            "same_day": item["same_day"],
            "contribution_low": item.get("contribution_low"),
            "contribution_high": item.get("contribution_high"),
        })
    totals = {
        "signed_refund_cents": -sum(s["signed_cents"] for s in signing if s["signed_cents"] < 0),
        "signed_charge_cents": sum(s["signed_cents"] for s in signing if s["signed_cents"] > 0),
        "signed_total_cents": sum(s["signed_cents"] for s in signing),
        "signed_tickets": sum(1 for s in signing if s["sign_state"] == "SIGNED"),
        "pending_tickets": sum(1 for s in signing if s["sign_state"] == "PENDING"),
        "blocked_tickets": sum(1 for s in signing if s["sign_state"] == "BLOCKED"),
    }
    return {"tickets": signing, "totals": totals}


def _claims(items):
    return [
        TicketClaim(index=idx, ticket_id=item[SPEC["key"]], direction=item["direction"],
                    cap=item["cap_cents"], has_evidence=item["evidence_cents"] is not None,
                    evidence=item["evidence_cents"] or 0)
        for idx, item in enumerate(items)
    ]


def apply_evidence(items, net_total, supplements):
    """把后补逐票凭据并入团单，重新分解并返回冲突票集合。

    supplements: {ticket_id: 有符号凭据金额（分）}
    冲突条件：凭据越界（方向/上限）、凭据与已签款不一致，或并入后净额无法再配平。
    """
    merged = [dict(item) for item in items]
    index = {item[SPEC["key"]]: item for item in merged}
    conflicts = {}
    for ticket_id, amount in supplements.items():
        item = index.get(ticket_id)
        if item is None:
            conflicts[ticket_id] = "TICKET_NOT_FOUND"
            continue
        amount = int(amount)
        if item["direction"] == "REFUND" and amount > 0:
            conflicts[ticket_id] = "EVIDENCE_DIRECTION"
            continue
        if item["direction"] == "CHARGE" and amount < 0:
            conflicts[ticket_id] = "EVIDENCE_DIRECTION"
            continue
        if abs(amount) > item["cap_cents"]:
            conflicts[ticket_id] = "EVIDENCE_OVER_CAP"
            continue
        item["evidence_cents"] = amount

    result = split_net(_claims(merged), net_total)
    if not result.feasible:
        # 净额对不上：所有后补票都暂缓，已签票保持原款
        for ticket_id in supplements:
            conflicts.setdefault(ticket_id, "NET_MISMATCH")
    return merged, conflicts, result
