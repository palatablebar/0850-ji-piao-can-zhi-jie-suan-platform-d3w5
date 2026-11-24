from app.errors import DomainIssue
from app.evidence.manifest import stable_digest


def render(run):
    if run is None:
        raise DomainIssue("RUN_NOT_FOUND", 404)
    if run["status"] != "APPROVED":
        raise DomainIssue("NOT_APPROVED", 409)
    signing = run.get("signing") or {"tickets": [], "totals": {}}
    artifact = {
        "schema": "workbench-evidence/v1",
        "run_id": run["run_id"],
        "project": run["project"],
        "rule": run["rule"],
        "profile": run["profile"],
        "source": run["source"],
        "counts": run["counts"],
        "ledger": run["ledger"],
        "summary": run["summary"],
        "signing_totals": signing.get("totals", {}),
        "tickets": [
            {
                "ticket_id": item["ticket_id"],
                "verdict": item["verdict"],
                "reason": item["reason"],
                "basis": item["basis"],
                "sign_state": item["sign_state"],
                "due_cents": item["due_cents"],
                "signed_cents": item["signed_cents"],
            }
            for item in signing.get("tickets", [])
        ],
        "supplement_log": run.get("supplement_log", []),
        "review": {"status": run["status"], "revision": run["revision"], "comment": run["comment"]},
    }
    artifact["artifact_sha256"] = stable_digest(artifact)
    return artifact
