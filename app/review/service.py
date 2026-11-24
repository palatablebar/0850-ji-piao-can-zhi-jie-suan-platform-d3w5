import json

from app.domain.decision import decide_rows
from app.domain.prepare import prepare_rows
from app.domain.settlement import apply_evidence, build_signing
from app.errors import DomainIssue
from app.intake.service import load
from app.reconcile.ledger import build_ledger
from app.review.policy import approval_allowed


def create_run(store, payload):
    row = store.create(payload["run_key"], payload["profile"], payload)
    return serialize(row)


def approve(store, run_id, decision, comment, expected_revision):
    row = store.get(run_id)
    if row is None:
        raise DomainIssue("RUN_NOT_FOUND", 404)
    payload = json.loads(row["payload"])
    if decision not in {"APPROVED", "HELD"}:
        raise DomainIssue("BAD_REQUEST")
    if decision == "APPROVED" and row["status"] != "APPROVED" and not approval_allowed(payload):
        raise DomainIssue("GATE_BLOCKED", 409)
    row, problem = store.review(run_id, decision, comment.strip(), expected_revision)
    if problem == "missing":
        raise DomainIssue("RUN_NOT_FOUND", 404)
    if problem == "stale":
        raise DomainIssue("STALE_REVIEW", 409)
    # 首次签发固化每张票的签发款；重试（problem == retried）不触碰实收实退
    if problem is None and row["status"] == "APPROVED" and payload.get("signing"):
        store.save_snapshot(run_id, {
            t["ticket_id"]: t["signed_cents"] for t in payload["signing"]["tickets"]
        })
    return serialize(row)


def supplement(store, run_id, body, expected_revision):
    """后补逐票凭据：对不上原净额或已签款时，余款暂缓签发。"""
    row = store.get(run_id)
    if row is None:
        raise DomainIssue("RUN_NOT_FOUND", 404)
    if row["revision"] != expected_revision:
        raise DomainIssue("STALE_REVIEW", 409)
    entries = body.get("evidence")
    if not isinstance(entries, dict) or not entries:
        raise DomainIssue("BAD_REQUEST")
    payload = json.loads(row["payload"])
    intake = load(payload["profile"])
    prepared, prepare_issues = prepare_rows(intake["rows"])
    net_values = {item["net_cents"] for item in prepared}
    if len(net_values) != 1:
        raise DomainIssue("GATE_BLOCKED", 409)
    net_total = next(iter(net_values))

    supplements = {str(k): int(v) for k, v in entries.items()}
    snapshot = store.get_snapshot(run_id)
    # 与已签款对不上：直接判冲突，已签款保持不变
    hard_conflicts = {}
    for ticket_id, amount in supplements.items():
        if ticket_id in snapshot and snapshot[ticket_id] != amount:
            hard_conflicts[ticket_id] = "SIGNED_AMOUNT_MISMATCH"
    pending = {k: v for k, v in supplements.items() if k not in hard_conflicts}
    merged, conflicts, _split = apply_evidence(prepared, net_total, pending)
    conflicts.update(hard_conflicts)

    from app.domain.calculate import calculate_rows
    results = decide_rows(calculate_rows(merged))
    signing = build_signing(results)
    # 冲突票一律暂缓，保留已签款，不新增款项
    for ticket in signing["tickets"]:
        if ticket["ticket_id"] in conflicts:
            ticket["sign_state"] = "PENDING" if ticket["sign_state"] != "SIGNED" else "SIGNED"
            ticket["hold_reason"] = conflicts[ticket["ticket_id"]]
            if ticket["sign_state"] == "PENDING":
                ticket["signed_cents"] = 0
    for ticket_id, reason in conflicts.items():
        store.record_supplement(run_id, ticket_id, supplements[ticket_id], False, reason)
    for ticket_id in supplements:
        if ticket_id not in conflicts:
            store.record_supplement(run_id, ticket_id, supplements[ticket_id], True, "ACCEPTED")

    ledger = build_ledger(intake, merged, prepare_issues, results, signing)
    payload["signing"] = signing
    payload["ledger"] = ledger
    payload["supplement_conflicts"] = conflicts
    payload["supplement_log"] = store.supplements(run_id)
    store.replace_payload(run_id, payload)
    return serialize(store.get(run_id)), conflicts


def serialize(row):
    if row is None:
        return None
    payload = json.loads(row["payload"])
    payload.update(run_id=row["id"], status=row["status"], revision=row["revision"],
                   comment=row["comment"], created_at=row["created_at"],
                   signed_snapshot=json.loads(row["signed_snapshot"] or "{}"))
    return payload
