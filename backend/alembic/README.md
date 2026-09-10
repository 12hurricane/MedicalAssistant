# Database migrations (MedAssist AI)

Async SQLAlchemy + Alembic. Run every command from `backend/` with the venv python.

The schema is owned by these migrations, **not** by `Base.metadata.create_all`.
`create_all` was removed from startup because it only ever creates *missing
tables*: add a column, change a type, add an index or a unique constraint to a
table that already exists and it reports success while doing none of it. The app
then runs against a schema that quietly disagrees with the models.

`app/core/lifespan.py` now refuses to start unless the database is stamped at
head. It does not auto-upgrade — that would race when several workers boot at
once, and would silently apply whatever destructive DDL happened to be pending.

## Everyday commands

```bash
# where is this database?
python -m alembic current

# apply everything outstanding
python -m alembic upgrade head

# do the models differ from the database? (exit code 1 if they do)
python -m alembic check

# after changing a model — always read the generated file before committing it
python -m alembic revision --autogenerate -m "add reminder retry count"
```

## Things specific to this project

**The URL comes from `settings.DATABASE_URL`, not `alembic.ini`.**
`sqlalchemy.url` is deliberately left unset so migrations and the running app
cannot be pointed at different databases. To migrate a different database, set
`DATABASE_URL` in the environment:

```bash
DATABASE_URL=sqlite+aiosqlite:///./scratch.db python -m alembic upgrade head
```

**`UTCDateTime` columns need no special handling.** `env.py` installs a
`render_item` hook that emits `app.models.types.UTCDateTime()` plus the matching
import. Without it, autogenerate would emit a type reference Alembic cannot
import and the migration would fail when run.

**Every model is imported automatically.** `env.py` does `import app.models`, so
a newly added model cannot be silently left out of autogenerate — provided it is
also exported from `app/models/__init__.py`.

**Batch mode is on for SQLite only.** SQLite cannot `ALTER` most things in
place, so `render_as_batch` rewrites the table instead. It is off for Postgres,
where it would mean needless table rebuilds.

**`compare_type` and `compare_server_default` are both on.** Autogenerate will
therefore notice type and default changes, not just added and dropped columns.
It still cannot see everything — always read the generated migration.

## Adopting a database that already exists

An older database built by `create_all` has the right tables but no
`alembic_version` row, so startup will refuse it. If its schema really does
match the models, adopt it without re-running the DDL:

```bash
python -m alembic check   # confirm it matches first
python -m alembic stamp head
```

`stamp` writes the version row and runs no DDL. Confirm with `check` first —
stamping a database that does *not* match the models replaces a loud startup
failure with a silent, wrong schema.

## Revisions

- `41a4374595d2` — baseline schema (11 tables). Generated against an empty
  database so it contains the full `CREATE TABLE` set, then verified three ways:
  the resulting schema is structurally identical to `create_all`'s, identical to
  the pre-existing `medication.db` (which is why stamping that database was
  honest), and `downgrade base` removes everything it created.
