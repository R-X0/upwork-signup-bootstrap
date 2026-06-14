#!/usr/bin/env python3
"""Print the most recent accounts saved to the Postgres database.

Usage:  python view_accounts.py [N]      (default 20)
Needs DATABASE_URL (or DATABASE_PUBLIC_URL) in .env / the environment.
"""
import sys
import db


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    if not db.available():
        raise SystemExit("DB not available — set DATABASE_URL and `pip install psycopg2-binary`")
    db.init_db()
    rows = db.recent(n)
    if not rows:
        print("(no accounts yet)")
        return
    print(f"{'id':>4}  {'created_at':<20} {'status':<18} {'email':<42} {'password':<14} {'machine'}")
    print("-" * 120)
    for r in rows:
        ts = str(r["created_at"])[:19]
        print(f"{r['id']:>4}  {ts:<20} {r['status']:<18} {r['email']:<42} {str(r['password'] or ''):<14} {r['machine']}")
    print(f"\n{len(rows)} row(s).")


if __name__ == "__main__":
    main()
