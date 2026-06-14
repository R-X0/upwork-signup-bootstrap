"""Single place that records a created account.

Writes a durable local JSONL ledger (cap/accounts.jsonl) AND, if a database is
configured, upserts the same record into Postgres. A DB failure is logged and
swallowed — it can never abort an account-creation run; the JSONL ledger is always
written first and remains the offline source of truth.

Every pipeline (sb_signup.py / hybrid.py) calls record() instead of writing files
directly, so all of them land in the same database.
"""
import os
import json
import time
import socket
import uuid

import config

CAP = config.CAP
_MACHINE = socket.gethostname() or "unknown-host"

# One run id per process so multiple status rows for the same account can be grouped.
RUN_ID = uuid.uuid4().hex[:12]

_db_ready = None  # tri-state: None=untried, True=ready, False=unavailable


def _write_jsonl(rec: dict) -> None:
    try:
        os.makedirs(CAP, exist_ok=True)
        with open(os.path.join(CAP, "accounts.jsonl"), "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec) + "\n")
    except Exception as e:
        print(f">>> [account_store] ledger write err: {e}", flush=True)


def _ensure_db() -> bool:
    global _db_ready
    if _db_ready is not None:
        return _db_ready
    try:
        import db
        if not db.available():
            print(">>> [account_store] no DATABASE_URL / psycopg2 — DB save disabled (local ledger only)", flush=True)
            _db_ready = False
            return False
        db.init_db()
        _db_ready = True
        print(">>> [account_store] database ready", flush=True)
    except Exception as e:
        print(f">>> [account_store] DB init failed (keeping local ledger only): {e}", flush=True)
        _db_ready = False
    return _db_ready


def record(status, email, password, first=None, last=None, pipeline=None, **extra) -> dict:
    """Persist one account status row. Returns the record dict."""
    rec = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "email": email,
        "password": password,
        "first": first,
        "last": last,
        "status": status,
        "pipeline": pipeline,
        "machine": _MACHINE,
        "run_id": RUN_ID,
    }
    rec.update(extra)
    _write_jsonl(rec)
    try:
        if _ensure_db():
            import db
            rid = db.insert_account(rec)
            print(f">>> [account_store] saved to DB id={rid}: {status} <{email}>", flush=True)
        else:
            print(f">>> [account_store] ledger += {status} <{email}> (no DB)", flush=True)
    except Exception as e:
        print(f">>> [account_store] DB save failed (kept local): {e}", flush=True)
    return rec
