"""Add heatmap materialized views for 8Knot

Creates three new materialized views needed by 8Knot for heatmap
visualizations (see 8Knot PR #1086). Views are created WITH NO DATA
so the migration runs fast; the refresh_materialized_views task will
populate them on its next run.

Revision ID: 39
Revises: 38
Create Date: 2026-03-31

"""
from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = '39'
down_revision = '38'
branch_labels = None
depends_on = None


def upgrade():

    conn = op.get_bind()

    # -- explorer_cntrb_per_file --
    # Contributors and reviewers per file path, aggregated from PRs.
    # Uses CAST(... AS text) instead of varchar(15) because BigInt can be 19 digits.
    conn.execute(text("""
        DROP MATERIALIZED VIEW IF EXISTS augur_data.explorer_cntrb_per_file;
    """))
    conn.execute(text("""
        CREATE MATERIALIZED VIEW augur_data.explorer_cntrb_per_file AS
        SELECT
            pr.repo_id AS repo_id,
            prf.pr_file_path AS file_path,
            string_agg(DISTINCT CAST(pr.pr_augur_contributor_id AS text), ',') AS cntrb_ids,
            string_agg(DISTINCT CAST(prr.cntrb_id AS text), ',') AS reviewer_ids
        FROM augur_data.pull_requests pr
        INNER JOIN augur_data.pull_request_files prf
            ON pr.pull_request_id = prf.pull_request_id
        LEFT OUTER JOIN augur_data.pull_request_reviews prr
            ON pr.pull_request_id = prr.pull_request_id
        GROUP BY prf.pr_file_path, pr.repo_id
        WITH NO DATA;
    """))
    conn.execute(text("""COMMIT;"""))

    conn = op.get_bind()
    conn.execute(text("""
        CREATE UNIQUE INDEX ON augur_data.explorer_cntrb_per_file(repo_id, file_path);
    """))
    conn.execute(text("""COMMIT;"""))

    # -- explorer_pr_files --
    # Distinct file paths per PR. DISTINCT protects the unique index from dirty data.
    conn = op.get_bind()
    conn.execute(text("""
        DROP MATERIALIZED VIEW IF EXISTS augur_data.explorer_pr_files;
    """))
    conn.execute(text("""
        CREATE MATERIALIZED VIEW augur_data.explorer_pr_files AS
        SELECT DISTINCT
            prf.pr_file_path AS file_path,
            pr.pull_request_id AS pull_request_id,
            pr.repo_id AS repo_id
        FROM augur_data.pull_requests pr
        INNER JOIN augur_data.pull_request_files prf
            ON pr.pull_request_id = prf.pull_request_id
        WITH NO DATA;
    """))
    conn.execute(text("""COMMIT;"""))

    conn = op.get_bind()
    conn.execute(text("""
        CREATE UNIQUE INDEX ON augur_data.explorer_pr_files(file_path, pull_request_id, repo_id);
    """))
    conn.execute(text("""COMMIT;"""))

    # -- explorer_repo_files --
    # Files from the most recent repo_labor analysis date per repo.
    # Uses repo_id (not id) per MoralCode's review feedback.
    conn = op.get_bind()
    conn.execute(text("""
        DROP MATERIALIZED VIEW IF EXISTS augur_data.explorer_repo_files;
    """))
    conn.execute(text("""
        CREATE MATERIALIZED VIEW augur_data.explorer_repo_files AS
        SELECT
            rl.repo_id AS repo_id,
            r.repo_name,
            r.repo_path,
            rl.rl_analysis_date,
            rl.file_path,
            rl.file_name
        FROM augur_data.repo_labor rl
        INNER JOIN augur_data.repo r
            ON rl.repo_id = r.repo_id
        WHERE (rl.repo_id, rl.rl_analysis_date) IN (
            SELECT DISTINCT ON (repo_id)
                repo_id, rl_analysis_date
            FROM augur_data.repo_labor
            ORDER BY repo_id, rl_analysis_date DESC
        )
        WITH NO DATA;
    """))
    conn.execute(text("""COMMIT;"""))

    conn = op.get_bind()
    conn.execute(text("""
        CREATE UNIQUE INDEX ON augur_data.explorer_repo_files(repo_id, file_path, file_name, rl_analysis_date);
    """))
    conn.execute(text("""COMMIT;"""))


def downgrade():

    conn = op.get_bind()
    conn.execute(text("""
        DROP MATERIALIZED VIEW IF EXISTS augur_data.explorer_cntrb_per_file;
        DROP MATERIALIZED VIEW IF EXISTS augur_data.explorer_pr_files;
        DROP MATERIALIZED VIEW IF EXISTS augur_data.explorer_repo_files;
    """))
