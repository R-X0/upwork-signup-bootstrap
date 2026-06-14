"""Postgres persistence for created accounts (dedicated Railway database).

Connection comes from DATABASE_URL (or DATABASE_PUBLIC_URL as a fallback so the
same .env works whether you run inside Railway or from an external machine).

This module is intentionally defensive: importing it never fails even if psycopg2
isn't installed, and every public function degrades gracefully so a database hiccup
can never abort an account-creation run (the JSONL ledger is still the source of
truth — see account_store.py).
"""
import os
import json

try:
    import psycopg2
    from psycopg2.extras import Json
except Exception:  # psycopg2 not installed yet (e.g. before requirements are pip-installed)
    psycopg2 = None
    Json = None

import config  # noqa: F401  (loads .env so DATABASE_URL is populated)


DDL = """
CREATE TABLE IF NOT EXISTS accounts (
    id          BIGSERIAL PRIMARY KEY,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    email       TEXT NOT NULL,
    password    TEXT,
    first_name  TEXT,
    last_name   TEXT,
    status      TEXT NOT NULL,
    final_url   TEXT,
    phone       TEXT,
    sms_code    TEXT,
    code        TEXT,
    err         TEXT,
    pipeline    TEXT,
    machine     TEXT,
    run_id      TEXT,
    extra       JSONB
);
CREATE INDEX IF NOT EXISTS idx_accounts_email  ON accounts(email);
CREATE INDEX IF NOT EXISTS idx_accounts_status ON accounts(status);
CREATE INDEX IF NOT EXISTS idx_accounts_created ON accounts(created_at);
"""

# Columns we store as real columns; everything else on a record lands in extra (JSONB).
_KNOWN = {"email", "password", "status", "final_url", "phone",
          "sms_code", "code", "err", "pipeline", "machine", "run_id"}
_ALIAS = {"first": "first_name", "last": "last_name"}


def db_url() -> str:
    return os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_PUBLIC_URL") or ""


def available() -> bool:
    """True only if we can actually talk to a database (driver present + URL set)."""
    return bool(psycopg2 and db_url())


def connect():
    url = db_url()
    if not url:
        raise RuntimeError("DATABASE_URL (or DATABASE_PUBLIC_URL) not set")
    if psycopg2 is None:
        raise RuntimeError("psycopg2 not installed — pip install psycopg2-binary")
    return psycopg2.connect(url, connect_timeout=15)


def init_db() -> None:
    """Create the accounts table + indexes if they don't exist (idempotent)."""
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(DDL)
        conn.commit()


def insert_account(rec: dict) -> int:
    """Insert one account record (a dict produced by account_store.record).

    Known keys map to columns; unknown keys are preserved in the extra JSONB blob,
    so adding new metadata later never needs a migration. Returns the new row id.
    """
    cols: dict = {}
    extra: dict = {}
    for k, v in rec.items():
        if k in _KNOWN:
            cols[k] = v
        elif k in _ALIAS:
            cols[_ALIAS[k]] = v
        else:
            extra[k] = v
    cols.setdefault("email", rec.get("email", ""))
    cols.setdefault("status", rec.get("status", "unknown"))

    fields = list(cols.keys()) + ["extra"]
    placeholders = ["%s"] * (len(cols) + 1)
    values = [cols[f] for f in cols]
    values.append(Json(extra) if Json else json.dumps(extra))

    sql = f"INSERT INTO accounts ({', '.join(fields)}) VALUES ({', '.join(placeholders)}) RETURNING id"
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, values)
            rid = cur.fetchone()[0]
        conn.commit()
    return rid


def recent(limit: int = 20):
    """Return the most recent accounts (list of dict rows) — used by view_accounts.py."""
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, created_at, email, password, status, phone, pipeline, machine "
                "FROM accounts ORDER BY id DESC LIMIT %s", (limit,))
            rows = cur.fetchall()
            cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in rows]


if __name__ == "__main__":
    # Quick self-test: create the table and print a count.
    if not available():
        raise SystemExit("DB not available — set DATABASE_URL and pip install psycopg2-binary")
    init_db()
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM accounts")
            print("accounts rows:", cur.fetchone()[0])
    print("db.py OK")
