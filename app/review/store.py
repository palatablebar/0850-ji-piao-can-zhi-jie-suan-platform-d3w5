import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.init()

    def connect(self):
        connection = sqlite3.connect(self.path, timeout=8)
        connection.row_factory = sqlite3.Row
        return connection

    def init(self):
        with self.connect() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS runs(
              id TEXT PRIMARY KEY,
              request_key TEXT UNIQUE NOT NULL,
              created_at TEXT NOT NULL,
              profile TEXT NOT NULL,
              status TEXT NOT NULL,
              revision INTEGER NOT NULL,
              payload TEXT NOT NULL,
              comment TEXT NOT NULL DEFAULT '',
              signed_snapshot TEXT NOT NULL DEFAULT '{}'
            );
            CREATE TABLE IF NOT EXISTS supplements(
              run_id TEXT NOT NULL,
              ticket_id TEXT NOT NULL,
              amount_cents INTEGER NOT NULL,
              accepted INTEGER NOT NULL,
              reason TEXT NOT NULL DEFAULT '',
              created_at TEXT NOT NULL,
              PRIMARY KEY(run_id, ticket_id)
            );
            ''')

    def find_by_request(self, request_key):
        with self.connect() as db:
            row = db.execute("SELECT * FROM runs WHERE request_key=?", (request_key,)).fetchone()
        return dict(row) if row else None

    def create(self, request_key, profile, payload):
        existing = self.find_by_request(request_key)
        if existing:
            return existing
        run_id = uuid.uuid4().hex[:12]
        with self.connect() as db:
            db.execute("INSERT INTO runs(id,request_key,created_at,profile,status,revision,payload) VALUES(?,?,?,?,?,?,?)",
                       (run_id, request_key, datetime.now(timezone.utc).isoformat(), profile, "DRAFT", 0,
                        json.dumps(payload, ensure_ascii=False)))
        return self.get(run_id)

    def get(self, run_id):
        with self.connect() as db:
            row = db.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        return dict(row) if row else None

    def review(self, run_id, decision, comment, expected_revision):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
            if row is None:
                return None, "missing"
            if row["revision"] != expected_revision:
                return None, "stale"
            # 已签发后再次签发属于重试：不新增实收实退，直接返回当前记录
            if row["status"] == "APPROVED" and decision == "APPROVED":
                return self.get(run_id), "retried"
            db.execute("UPDATE runs SET status=?, revision=revision+1, comment=? WHERE id=?",
                       (decision, comment, run_id))
        return self.get(run_id), None

    def save_snapshot(self, run_id, snapshot):
        with self.connect() as db:
            db.execute("UPDATE runs SET signed_snapshot=? WHERE id=?",
                       (json.dumps(snapshot, ensure_ascii=False), run_id))

    def replace_payload(self, run_id, payload):
        with self.connect() as db:
            db.execute("UPDATE runs SET payload=? WHERE id=?",
                       (json.dumps(payload, ensure_ascii=False), run_id))

    def get_snapshot(self, run_id):
        row = self.get(run_id)
        if not row:
            return {}
        return json.loads(row["signed_snapshot"] or "{}")

    def record_supplement(self, run_id, ticket_id, amount, accepted, reason):
        with self.connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO supplements(run_id,ticket_id,amount_cents,accepted,reason,created_at) "
                "VALUES(?,?,?,?,?,?)",
                (run_id, ticket, int(amount), 1 if accepted else 0, reason,
                 datetime.now(timezone.utc).isoformat()))

    def supplements(self, run_id):
        with self.connect() as db:
            rows = db.execute("SELECT * FROM supplements WHERE run_id=? ORDER BY created_at", (run_id,)).fetchall()
        return [dict(row) for row in rows]
