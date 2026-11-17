# Step 05 — Mind database and migrations

**Goal:** `mind.sqlite` is created and upgraded only by numbered migration
files, never by hand.

**Why this matters:** saves must keep working for years. Every schema change
from now on is a new migration file (`0002_…`, `0003_…`) that upgrades old
saves forward. You never edit a migration once it has been committed.

## 5.1 The migration runner

`mind_service/src/mind/storage/db.py`
```python
"""SQLite connection + forward-only migrations for mind.sqlite."""
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def connect(path: Path | str) -> sqlite3.Connection:
    # isolation_level=None: autocommit; we open transactions explicitly.
    con = sqlite3.connect(path, isolation_level=None)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    return con


def migrate(con: sqlite3.Connection, migrations_dir: Path = MIGRATIONS_DIR) -> int:
    """Apply every NNNN_*.sql not yet applied. Returns the schema version."""
    con.execute("CREATE TABLE IF NOT EXISTS schema_migrations "
                "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)")
    applied = {row[0] for row in con.execute("SELECT version FROM schema_migrations")}
    for f in sorted(migrations_dir.glob("*.sql")):
        version = int(f.name.split("_", 1)[0])
        if version in applied:
            continue
        now = datetime.now(timezone.utc).isoformat()
        try:
            con.executescript(
                f"BEGIN;\n{f.read_text(encoding='utf-8')}\n"
                f"INSERT INTO schema_migrations VALUES ({version}, '{now}');\nCOMMIT;")
        except Exception:
            if con.in_transaction:
                con.execute("ROLLBACK")
            raise
    return schema_version(con)


def schema_version(con: sqlite3.Connection) -> int:
    return con.execute("SELECT COALESCE(MAX(version), 0) FROM schema_migrations").fetchone()[0]
```

Key points:
- `isolation_level=None` means Python won't open transactions behind your back.
  The runner wraps each migration in its own `BEGIN … COMMIT`, so a failing
  migration leaves the database untouched.
- WAL mode lets saves (`VACUUM INTO`, step 11) run while the database is open.
- Foreign keys are **off by default in SQLite**. They must be turned on for
  every connection, which `connect()` does.

## 5.2 The first migration

Create `mind_service/src/mind/storage/migrations/0001_init.sql` by copying the
`mind.sqlite` schema from `docs/architecture/06-data-architecture.md §3`, with
**one change**: delete its first line, `CREATE TABLE schema_migrations …`. The
runner creates that table itself.

The top of the file should read:
```sql
-- mind.sqlite schema v1 (from docs/architecture/06-data-architecture.md §3)
-- schema_migrations is created by the migration runner, not here.
CREATE TABLE mind_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
```

## 5.3 Tests

`mind_service/tests/test_migrations.py`
```python
from mind.storage.db import connect, migrate


def test_migrate_creates_schema_and_is_idempotent(tmp_path):
    con = connect(tmp_path / "mind.sqlite")
    assert migrate(con) == 1
    assert migrate(con) == 1          # running twice changes nothing
    tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"agents", "beliefs", "memories", "goals", "llm_calls"} <= tables


def test_foreign_keys_enforced(tmp_path):
    import sqlite3, pytest
    con = connect(tmp_path / "mind.sqlite")
    migrate(con)
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("INSERT INTO perceived_needs VALUES ('nobody', 'thirst', 0.5, 0.5, 0)")
```

## Check it works

```bash
pytest -q tests/test_migrations.py     # → 2 passed
```

## Rules from now on

1. **Never edit `0001_init.sql` after you commit it.** Add `0002_<what>.sql` instead.
2. Migrations only move forward. There are no "down" migrations, because saves
   only move forward too.
3. Every migration gets a test that runs it on a database at the previous
   version.

## Common mistakes

- **Leaving the `schema_migrations` line in 0001.** You get the error "table
  schema_migrations already exists".
- **Writing a migration that only works on an empty database**, such as adding
  a `NOT NULL` column with no `DEFAULT`. That breaks every existing save.
