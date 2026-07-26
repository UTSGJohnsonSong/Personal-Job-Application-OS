"""Collapse duplicate scoring rows and make one-row-per-job structural.

`score_job` inserted a new row on every run instead of updating, and neither
`application_priority_scores` nor `role_classifications` had a uniqueness
constraint. `score_all_jobs` walks the entire jobs table, so every recompute or
pool refresh multiplied both tables: by 2026-07-25 they held 111,166 rows for
10,923 jobs (10.2x), and the database file had grown to ~437 MB.

Worse than the size: rows for the same job could DISAGREE. The location read in
`score_job` used `.limit(1)` with no ORDER BY, so multi-city postings picked a
different city per run, and location is a hard eligibility input — the same job
carried PASS in one row and REVIEW in another. Every reader hid this by taking
"latest by created_at", which made the contradiction survivable rather than
impossible.

DEPLOY ORDER — this matters and there is no safe concurrent option:

    1. stop the API and any refresh worker
    2. back up the database
    3. run this migration
    4. start the new code

New code against an un-migrated database raises `ScoringDataError` on every
job (it refuses to guess which of several rows to update). Old code against a
migrated database hits `uq_priority_score` and raises `IntegrityError` on every
insert. `docker-entrypoint.sh` already runs `alembic upgrade head` before
starting uvicorn, so the standard container path is safe; a rollback to a
previous image, or a hand-started worker, is not.

Deletion is irreversible. `downgrade` drops the constraints only — it restores
the old shape, not the old contents, and does not pretend otherwise.

Revision ID: b1c74e9a2f30
Revises: f60de245306b
Create Date: 2026-07-25
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b1c74e9a2f30"
down_revision = "f60de245306b"
branch_labels = None
depends_on = None


# Keep one row per group.
#
# `manually_overridden DESC` leads deliberately. The rest of the ordering keeps
# the newest row, which is what every reader already took client-side
# (scoring_v2.latest_scores, services/inbox.load_companies,
# services/pool._live_roles) — but a user override is a human judgement that
# cannot be recomputed, and if it happened to sit on an older row, "newest wins"
# would delete it with no way back. Correctness of the surviving numbers is
# unaffected: the next recompute refreshes them either way.
#
# `id DESC` is only a tiebreak for equal `created_at`, which is common because a
# batch run stamps many rows within the same instant. Readers have no tiebreak
# there at all, so for tied rows the row kept here may differ from the one a
# reader would have shown; the values are from the same run, and the next
# recompute overwrites them regardless.
_DEDUPE_PRIORITY = """
DELETE FROM application_priority_scores
WHERE id NOT IN (
    SELECT id FROM (
        SELECT id,
               ROW_NUMBER() OVER (
                   PARTITION BY job_id, user_id, ranking_mode
                   ORDER BY manually_overridden DESC, created_at DESC, id DESC
               ) AS rn
        FROM application_priority_scores
    ) ranked
    WHERE rn = 1
)
"""

_DEDUPE_ROLES = """
DELETE FROM role_classifications
WHERE id NOT IN (
    SELECT id FROM (
        SELECT id,
               ROW_NUMBER() OVER (
                   PARTITION BY job_id
                   ORDER BY created_at DESC, id DESC
               ) AS rn
        FROM role_classifications
    ) ranked
    WHERE rn = 1
)
"""


def _collapse(bind, table: str, group_by: str, statement: str) -> None:
    """Run one dedupe and refuse to continue if the result is not what we expect.

    An unattended `DELETE` over ~100k rows should not be able to remove the
    wrong number of them in silence. Deleting everything and deleting nothing
    currently produce identical output, and `docker-entrypoint.sh` runs this
    with nobody watching.
    """
    before = bind.execute(sa.text(f"SELECT COUNT(*) FROM {table}")).scalar_one()
    expected = bind.execute(
        sa.text(f"SELECT COUNT(*) FROM (SELECT DISTINCT {group_by} FROM {table}) d")
    ).scalar_one()

    bind.execute(sa.text(statement))

    after = bind.execute(sa.text(f"SELECT COUNT(*) FROM {table}")).scalar_one()
    if after != expected:
        raise RuntimeError(
            f"{table}: dedupe left {after} rows but {expected} distinct "
            f"({group_by}) groups exist (started at {before}). Aborting before "
            f"the unique constraint is added — the database is unchanged only "
            f"if your engine wraps DDL in a transaction (Postgres does; SQLite "
            f"does not, so restore from backup)."
        )
    print(f"[b1c74e9a2f30] {table}: {before} -> {after} ({before - after} removed)")


def upgrade() -> None:
    bind = op.get_bind()
    _collapse(bind, "application_priority_scores",
              "job_id, user_id, ranking_mode", _DEDUPE_PRIORITY)
    _collapse(bind, "role_classifications", "job_id", _DEDUPE_ROLES)

    # batch_alter_table so this also works on SQLite, which cannot ALTER TABLE
    # ADD CONSTRAINT and needs the copy-and-rename dance (DECISIONS.md D1:
    # SQLite in dev/tests, Postgres in production — this runs on both). On
    # Postgres it is a passthrough emitting plain ALTER TABLE ADD CONSTRAINT.
    with op.batch_alter_table("application_priority_scores") as batch:
        batch.create_unique_constraint(
            "uq_priority_score", ["job_id", "user_id", "ranking_mode"]
        )
    with op.batch_alter_table("role_classifications") as batch:
        batch.create_unique_constraint("uq_role_classification_job", ["job_id"])


def downgrade() -> None:
    # Drops the constraints only. The de-duplicated rows are gone; a downgrade
    # restores the old shape, not the old contents.
    with op.batch_alter_table("role_classifications") as batch:
        batch.drop_constraint("uq_role_classification_job", type_="unique")
    with op.batch_alter_table("application_priority_scores") as batch:
        batch.drop_constraint("uq_priority_score", type_="unique")
