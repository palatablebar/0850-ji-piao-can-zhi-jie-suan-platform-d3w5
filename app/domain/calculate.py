from app.catalog import SPEC
from app.domain.net_split import SplitResult, TicketClaim, split_net


def _group(items):
    """一个批次预期只处理一个团单；同批出现多个团单号则阻断。"""
    order_ids = {item["order_id"] for item in items}
    if len(order_ids) > 1:
        return None, "ORDER_MIX"
    net_values = {item["net_cents"] for item in items}
    if len(net_values) != 1:
        return None, "NET_INCONSISTENT"
    return net_values.pop(), None


def _signed(direction, contribution):
    return -contribution if direction == "REFUND" else contribution


def calculate_rows(items):
    """按团单净额分解出每张票的应结金额。

    - 已核准逐票凭据：直接采信，先从净额扣除；
    - 缺逐票凭据：在方向与上限内求所有可行拆法，记录该票贡献的可行闭区间。
    """
    net_total, group_issue = _group(items)
    tickets = [
        TicketClaim(index=idx, ticket_id=item[SPEC["key"]], direction=item["direction"],
                    cap=item["cap_cents"], has_evidence=item["evidence_cents"] is not None,
                    evidence=item["evidence_cents"] or 0)
        for idx, item in enumerate(items)
    ]
    result: SplitResult = SplitResult(False, 0, [], "NO_GROUP")
    if group_issue is None:
        result = split_net(tickets, net_total)

    variable_iter = iter(result.ranges)
    out = []
    for item, ticket in zip(items, tickets):
        row = dict(item)
        row.setdefault("label", str(item.get(SPEC["key"], "")))
        row["group_net_cents"] = net_total if group_issue is None else None
        row["group_issue"] = group_issue or ""
        if ticket.has_evidence:
            row["due_cents"] = ticket.evidence
            row["contribution_low"] = abs(ticket.evidence)
            row["contribution_high"] = abs(ticket.evidence)
            row["basis"] = "EVIDENCE"
        else:
            low, high = next(variable_iter) if result.feasible else (0, ticket.cap)
            row["contribution_low"] = low
            row["contribution_high"] = high
            row["due_cents"] = _signed(ticket.direction, low) if low == high else None
            row["basis"] = "NET_UNIQUE" if low == high else "NET_AMBIGUOUS"
        row["net_feasible"] = result.feasible
        row["net_reason"] = result.reason
        row["metric"] = abs(row["due_cents"]) if row["due_cents"] is not None else None
        row["limit"] = ticket.cap
        out.append(row)
    return out
