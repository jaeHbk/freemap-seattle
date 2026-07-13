#!/usr/bin/env python3
"""One-shot Turso schema init: run db/schema.sql against the Turso DB.

Idempotent (schema is all CREATE ... IF NOT EXISTS), so re-running is safe.
Refuses to run unless BOTH TURSO_DATABASE_URL and TURSO_AUTH_TOKEN are in the
env — it never reads or embeds a token from anywhere else.

    python -m scripts.migrate_turso        # from repo root
    ./.venv/bin/python -m scripts.migrate_turso

Local dev does NOT need this: scrapers/db.py creates the schema in db/deals.db
on its own. This script exists only to provision the remote Turso DB once.
"""
import os
import sys
from pathlib import Path

# schema.sql is the committed source of truth, same file scrapers.db.init_db() runs.
_SCHEMA_PATH = Path(__file__).resolve().parent.parent / "db" / "schema.sql"


def main() -> int:
    url = os.environ.get("TURSO_DATABASE_URL")
    token = os.environ.get("TURSO_AUTH_TOKEN")
    if not url or not token:
        print(
            "Refusing to run: set both TURSO_DATABASE_URL and TURSO_AUTH_TOKEN "
            "(see .env.example). This script only provisions a remote Turso DB; "
            "local dev uses db/deals.db automatically.",
            file=sys.stderr,
        )
        return 1

    import libsql  # imported here so local dev/tests never require the dep

    schema = _SCHEMA_PATH.read_text()
    conn = libsql.connect(url, auth_token=token)
    try:
        try:
            conn.executescript(schema)
        except AttributeError:
            # ponytail: fallback if a client build lacks executescript — schema has
            # no string literals with ';', so a naive split is safe here.
            for stmt in filter(str.strip, schema.split(";")):
                conn.execute(stmt)
        conn.commit()
        # Prove the schema actually reached the remote. executescript()+commit()
        # can buffer and return without error against an unreachable host / bad
        # token in this client, so a clean return is NOT proof of provisioning.
        # A SELECT forces a real round-trip: it raises on a bad host/token, and
        # confirms the table exists on success. Without this read-back the script
        # could report success against an UNprovisioned DB.
        try:
            n = conn.execute(
                "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='deals'"
            ).fetchone()[0]
        except Exception as e:
            # A bad host/token/network surfaces HERE (the SELECT round-trips),
            # not on executescript/commit. Report cleanly; never echo the token.
            print(f"Could not verify schema against the remote DB: {e}", file=sys.stderr)
            return 1
    finally:
        conn.close()

    if n != 1:
        print(
            "Schema did not apply: 'deals' table not found after migration.",
            file=sys.stderr,
        )
        return 1

    # Don't echo the URL — it identifies the prod DB. Confirm success only.
    print("Turso schema applied and verified (idempotent).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
