"""Centralized registry of all PostgreSQL materialized views in Augur.

This module is the single source of truth for materialized view definitions.
The refresh task iterates over MATERIALIZED_VIEWS to refresh all views.
Alembic migrations for NEW views should inline their SQL (migrations are
immutable snapshots), but this registry is the canonical reference for what
views exist and how to refresh them.

FUTURE: To enable alembic_utils autogenerate support for materialized views:

1. Add alembic-utils>=0.8.8 to pyproject.toml and run `uv lock`

2. Verify each view's SQL definition matches what PostgreSQL stores internally.
   Run on a live database:
     SELECT matviewname, definition FROM pg_matviews WHERE schemaname = 'augur_data';
   Compare the normalized output to the definitions in this module.
   PostgreSQL normalizes SQL (adds schema prefixes, reorders clauses, etc.)

3. Create PGMaterializedView objects from the definitions in this module
   and register them in env.py (after target_metadata line):
     from alembic_utils.replaceable_entity import register_entities
     register_entities([...all PGMaterializedView objects...])

4. Then `alembic revision --autogenerate` will detect view definition changes.
   WARNING: ALL views must be registered or autogenerate will propose dropping
   unregistered ones.

5. alembic_utils does NOT manage indexes on materialized views.
   Unique indexes must still be created manually in migrations.

6. The TSC goal for phase 2: keep auto-generating until the Python alembic defs
   match the SQL queries (essentially no upgrade or downgrade).
"""


# ---------------------------------------------------------------------------
# View 1: api_get_all_repo_prs (source: migration 4, index: migration 25)
# ---------------------------------------------------------------------------
_API_GET_ALL_REPO_PRS = """\
SELECT pull_requests.repo_id,
    count(*) AS pull_requests_all_time
FROM augur_data.pull_requests
GROUP BY pull_requests.repo_id"""

# ---------------------------------------------------------------------------
# View 2: explorer_entry_list (source: migration 4, index: migration 25)
# ---------------------------------------------------------------------------
_EXPLORER_ENTRY_LIST = """\
SELECT DISTINCT r.repo_git,
    r.repo_id,
    r.repo_name,
    rg.rg_name
FROM (augur_data.repo r
  JOIN augur_data.repo_groups rg ON ((rg.repo_group_id = r.repo_group_id)))
ORDER BY rg.rg_name"""

# ---------------------------------------------------------------------------
# View 3: explorer_commits_and_committers_daily_count
#   (source: migration 4, index: migration 25)
# ---------------------------------------------------------------------------
_EXPLORER_COMMITS_AND_COMMITTERS_DAILY_COUNT = """\
SELECT repo.repo_id,
    repo.repo_name,
    commits.cmt_committer_date,
    count(commits.cmt_id) AS num_of_commits,
    count(DISTINCT commits.cmt_committer_raw_email) AS num_of_unique_committers
FROM (augur_data.commits
    LEFT JOIN augur_data.repo ON ((repo.repo_id = commits.repo_id)))
GROUP BY repo.repo_id, repo.repo_name, commits.cmt_committer_date
ORDER BY repo.repo_id, commits.cmt_committer_date"""

# ---------------------------------------------------------------------------
# View 4: api_get_all_repos_commits (source: migration 4, index: migration 25)
# ---------------------------------------------------------------------------
_API_GET_ALL_REPOS_COMMITS = """\
SELECT commits.repo_id,
    count(DISTINCT commits.cmt_commit_hash) AS commits_all_time
FROM augur_data.commits
GROUP BY commits.repo_id"""

# ---------------------------------------------------------------------------
# View 5: api_get_all_repos_issues (source: migration 4, index: migration 25)
# ---------------------------------------------------------------------------
_API_GET_ALL_REPOS_ISSUES = """\
SELECT issues.repo_id,
    count(*) AS issues_all_time
FROM augur_data.issues
WHERE (issues.pull_request IS NULL)
GROUP BY issues.repo_id"""

# ---------------------------------------------------------------------------
# View 6: augur_new_contributors (source: migration 25, recreated)
# ---------------------------------------------------------------------------
_AUGUR_NEW_CONTRIBUTORS = """\
SELECT a.id AS cntrb_id,
    a.created_at,
    a.repo_id,
    a.action,
    repo.repo_name,
    a.login,
    row_number() OVER (PARTITION BY a.id, a.repo_id ORDER BY a.created_at DESC) AS rank
   FROM ( SELECT commits.cmt_ght_author_id AS id,
            commits.cmt_author_timestamp AS created_at,
            commits.repo_id,
            'commit'::text AS action,
            contributors.cntrb_login AS login
           FROM (augur_data.commits
             LEFT JOIN augur_data.contributors ON (((contributors.cntrb_id)::text = (commits.cmt_ght_author_id)::text)))
          GROUP BY commits.cmt_commit_hash, commits.cmt_ght_author_id, commits.repo_id, commits.cmt_author_timestamp, 'commit'::text, contributors.cntrb_login
        UNION ALL
         SELECT issues.reporter_id AS id,
            issues.created_at,
            issues.repo_id,
            'issue_opened'::text AS action,
            contributors.cntrb_login AS login
           FROM (augur_data.issues
             LEFT JOIN augur_data.contributors ON ((contributors.cntrb_id = issues.reporter_id)))
          WHERE (issues.pull_request IS NULL)
        UNION ALL
         SELECT pull_request_events.cntrb_id AS id,
            pull_request_events.created_at,
            pull_requests.repo_id,
            'pull_request_closed'::text AS action,
            contributors.cntrb_login AS login
           FROM augur_data.pull_requests,
            (augur_data.pull_request_events
             LEFT JOIN augur_data.contributors ON ((contributors.cntrb_id = pull_request_events.cntrb_id)))
          WHERE ((pull_requests.pull_request_id = pull_request_events.pull_request_id) AND (pull_requests.pr_merged_at IS NULL) AND ((pull_request_events.action)::text = 'closed'::text))
        UNION ALL
         SELECT pull_request_events.cntrb_id AS id,
            pull_request_events.created_at,
            pull_requests.repo_id,
            'pull_request_merged'::text AS action,
            contributors.cntrb_login AS login
           FROM augur_data.pull_requests,
            (augur_data.pull_request_events
             LEFT JOIN augur_data.contributors ON ((contributors.cntrb_id = pull_request_events.cntrb_id)))
          WHERE ((pull_requests.pull_request_id = pull_request_events.pull_request_id) AND ((pull_request_events.action)::text = 'merged'::text))
        UNION ALL
         SELECT issue_events.cntrb_id AS id,
            issue_events.created_at,
            issues.repo_id,
            'issue_closed'::text AS action,
            contributors.cntrb_login AS login
           FROM augur_data.issues,
            (augur_data.issue_events
             LEFT JOIN augur_data.contributors ON ((contributors.cntrb_id = issue_events.cntrb_id)))
          WHERE ((issues.issue_id = issue_events.issue_id) AND (issues.pull_request IS NULL) AND ((issue_events.action)::text = 'closed'::text))
        UNION ALL
         SELECT pull_request_reviews.cntrb_id AS id,
            pull_request_reviews.pr_review_submitted_at AS created_at,
            pull_requests.repo_id,
            ('pull_request_review_'::text || (pull_request_reviews.pr_review_state)::text) AS action,
            contributors.cntrb_login AS login
           FROM augur_data.pull_requests,
            (augur_data.pull_request_reviews
             LEFT JOIN augur_data.contributors ON ((contributors.cntrb_id = pull_request_reviews.cntrb_id)))
          WHERE (pull_requests.pull_request_id = pull_request_reviews.pull_request_id)
        UNION ALL
         SELECT pull_requests.pr_augur_contributor_id AS id,
            pull_requests.pr_created_at AS created_at,
            pull_requests.repo_id,
            'pull_request_open'::text AS action,
            contributors.cntrb_login AS login
           FROM (augur_data.pull_requests
             LEFT JOIN augur_data.contributors ON ((pull_requests.pr_augur_contributor_id = contributors.cntrb_id)))
        UNION ALL
         SELECT message.cntrb_id AS id,
            message.msg_timestamp AS created_at,
            pull_requests.repo_id,
            'pull_request_comment'::text AS action,
            contributors.cntrb_login AS login
           FROM augur_data.pull_requests,
            augur_data.pull_request_message_ref,
            (augur_data.message
             LEFT JOIN augur_data.contributors ON ((contributors.cntrb_id = message.cntrb_id)))
          WHERE ((pull_request_message_ref.pull_request_id = pull_requests.pull_request_id) AND (pull_request_message_ref.msg_id = message.msg_id))
        UNION ALL
         SELECT issues.reporter_id AS id,
            message.msg_timestamp AS created_at,
            issues.repo_id,
            'issue_comment'::text AS action,
            contributors.cntrb_login AS login
           FROM augur_data.issues,
            augur_data.issue_message_ref,
            (augur_data.message
             LEFT JOIN augur_data.contributors ON ((contributors.cntrb_id = message.cntrb_id)))
          WHERE ((issue_message_ref.msg_id = message.msg_id) AND (issues.issue_id = issue_message_ref.issue_id) AND (issues.closed_at <> message.msg_timestamp))) a,
    augur_data.repo
  WHERE (a.repo_id = repo.repo_id)
  ORDER BY a.created_at DESC"""

# ---------------------------------------------------------------------------
# View 7: explorer_contributor_actions (source: migration 25, recreated)
# ---------------------------------------------------------------------------
_EXPLORER_CONTRIBUTOR_ACTIONS = """\
SELECT a.id AS cntrb_id,
    a.created_at,
    a.repo_id,
    a.action,
    repo.repo_name,
    a.login,
    row_number() OVER (PARTITION BY a.id, a.repo_id ORDER BY a.created_at desc) AS rank
   FROM ( SELECT commits.cmt_ght_author_id AS id,
            commits.cmt_author_timestamp AS created_at,
            commits.repo_id,
            'commit'::text AS action,
            contributors.cntrb_login AS login
           FROM (augur_data.commits
             LEFT JOIN augur_data.contributors ON (((contributors.cntrb_id)::text = (commits.cmt_ght_author_id)::text)))
          GROUP BY commits.cmt_commit_hash, commits.cmt_ght_author_id, commits.repo_id, commits.cmt_author_timestamp, 'commit'::text, contributors.cntrb_login
        UNION ALL
         SELECT issues.reporter_id AS id,
            issues.created_at,
            issues.repo_id,
            'issue_opened'::text AS action,
            contributors.cntrb_login AS login
           FROM (augur_data.issues
             LEFT JOIN augur_data.contributors ON ((contributors.cntrb_id = issues.reporter_id)))
          WHERE (issues.pull_request IS NULL)
        UNION ALL
         SELECT pull_request_events.cntrb_id AS id,
            pull_request_events.created_at,
            pull_requests.repo_id,
            'pull_request_closed'::text AS action,
            contributors.cntrb_login AS login
           FROM augur_data.pull_requests,
            (augur_data.pull_request_events
             LEFT JOIN augur_data.contributors ON ((contributors.cntrb_id = pull_request_events.cntrb_id)))
          WHERE ((pull_requests.pull_request_id = pull_request_events.pull_request_id) AND (pull_requests.pr_merged_at IS NULL) AND ((pull_request_events.action)::text = 'closed'::text))
        UNION ALL
         SELECT pull_request_events.cntrb_id AS id,
            pull_request_events.created_at,
            pull_requests.repo_id,
            'pull_request_merged'::text AS action,
            contributors.cntrb_login AS login
           FROM augur_data.pull_requests,
            (augur_data.pull_request_events
             LEFT JOIN augur_data.contributors ON ((contributors.cntrb_id = pull_request_events.cntrb_id)))
          WHERE ((pull_requests.pull_request_id = pull_request_events.pull_request_id) AND ((pull_request_events.action)::text = 'merged'::text))
        UNION ALL
         SELECT issue_events.cntrb_id AS id,
            issue_events.created_at,
            issues.repo_id,
            'issue_closed'::text AS action,
            contributors.cntrb_login AS login
           FROM augur_data.issues,
            (augur_data.issue_events
             LEFT JOIN augur_data.contributors ON ((contributors.cntrb_id = issue_events.cntrb_id)))
          WHERE ((issues.issue_id = issue_events.issue_id) AND (issues.pull_request IS NULL) AND ((issue_events.action)::text = 'closed'::text))
        UNION ALL
         SELECT pull_request_reviews.cntrb_id AS id,
            pull_request_reviews.pr_review_submitted_at AS created_at,
            pull_requests.repo_id,
            ('pull_request_review_'::text || (pull_request_reviews.pr_review_state)::text) AS action,
            contributors.cntrb_login AS login
           FROM augur_data.pull_requests,
            (augur_data.pull_request_reviews
             LEFT JOIN augur_data.contributors ON ((contributors.cntrb_id = pull_request_reviews.cntrb_id)))
          WHERE (pull_requests.pull_request_id = pull_request_reviews.pull_request_id)
        UNION ALL
         SELECT pull_requests.pr_augur_contributor_id AS id,
            pull_requests.pr_created_at AS created_at,
            pull_requests.repo_id,
            'pull_request_open'::text AS action,
            contributors.cntrb_login AS login
           FROM (augur_data.pull_requests
             LEFT JOIN augur_data.contributors ON ((pull_requests.pr_augur_contributor_id = contributors.cntrb_id)))
        UNION ALL
         SELECT message.cntrb_id AS id,
            message.msg_timestamp AS created_at,
            pull_requests.repo_id,
            'pull_request_comment'::text AS action,
            contributors.cntrb_login AS login
           FROM augur_data.pull_requests,
            augur_data.pull_request_message_ref,
            (augur_data.message
             LEFT JOIN augur_data.contributors ON ((contributors.cntrb_id = message.cntrb_id)))
          WHERE ((pull_request_message_ref.pull_request_id = pull_requests.pull_request_id) AND (pull_request_message_ref.msg_id = message.msg_id))
        UNION ALL
         SELECT issues.reporter_id AS id,
            message.msg_timestamp AS created_at,
            issues.repo_id,
            'issue_comment'::text AS action,
            contributors.cntrb_login AS login
           FROM augur_data.issues,
            augur_data.issue_message_ref,
            (augur_data.message
             LEFT JOIN augur_data.contributors ON ((contributors.cntrb_id = message.cntrb_id)))
          WHERE ((issue_message_ref.msg_id = message.msg_id) AND (issues.issue_id = issue_message_ref.issue_id) AND (issues.closed_at <> message.msg_timestamp))) a,
    augur_data.repo
  WHERE (a.repo_id = repo.repo_id)
  ORDER BY a.created_at DESC"""

# ---------------------------------------------------------------------------
# View 8: explorer_new_contributors (source: migration 25, recreated)
# ---------------------------------------------------------------------------
_EXPLORER_NEW_CONTRIBUTORS = """\
SELECT x.cntrb_id,
    x.created_at,
    x.month,
    x.year,
    x.repo_id,
    x.repo_name,
    x.full_name,
    x.login,
    x.rank
   FROM ( SELECT b.cntrb_id,
            b.created_at,
            b.month,
            b.year,
            b.repo_id,
            b.repo_name,
            b.full_name,
            b.login,
            b.action,
            b.rank
           FROM ( SELECT a.id AS cntrb_id,
                    a.created_at,
                    date_part('month'::text, (a.created_at)::date) AS month,
                    date_part('year'::text, (a.created_at)::date) AS year,
                    a.repo_id,
                    repo.repo_name,
                    a.full_name,
                    a.login,
                    a.action,
                    row_number() OVER (PARTITION BY a.id, a.repo_id ORDER BY a.created_at desc) AS rank
                   FROM ( SELECT canonical_full_names.canonical_id AS id,
                            issues.created_at,
                            issues.repo_id,
                            'issue_opened'::text AS action,
                            contributors.cntrb_full_name AS full_name,
                            contributors.cntrb_login AS login
                           FROM ((augur_data.issues
                             LEFT JOIN augur_data.contributors ON ((contributors.cntrb_id = issues.reporter_id)))
                             LEFT JOIN ( SELECT DISTINCT ON (contributors_1.cntrb_canonical) contributors_1.cntrb_full_name,
                                    contributors_1.cntrb_canonical AS canonical_email,
                                    contributors_1.data_collection_date,
                                    contributors_1.cntrb_id AS canonical_id
                                   FROM augur_data.contributors contributors_1
                                  WHERE ((contributors_1.cntrb_canonical)::text = (contributors_1.cntrb_email)::text)
                                  ORDER BY contributors_1.cntrb_canonical) canonical_full_names ON (((canonical_full_names.canonical_email)::text = (contributors.cntrb_canonical)::text)))
                          WHERE (issues.pull_request IS NULL)
                          GROUP BY canonical_full_names.canonical_id, issues.repo_id, issues.created_at, contributors.cntrb_full_name, contributors.cntrb_login
                        UNION ALL
                         SELECT canonical_full_names.canonical_id AS id,
                            to_timestamp((commits.cmt_author_date)::text, 'YYYY-MM-DD'::text) AS created_at,
                            commits.repo_id,
                            'commit'::text AS action,
                            contributors.cntrb_full_name AS full_name,
                            contributors.cntrb_login AS login
                           FROM ((augur_data.commits
                             LEFT JOIN augur_data.contributors ON (((contributors.cntrb_canonical)::text = (commits.cmt_author_email)::text)))
                             LEFT JOIN ( SELECT DISTINCT ON (contributors_1.cntrb_canonical) contributors_1.cntrb_full_name,
                                    contributors_1.cntrb_canonical AS canonical_email,
                                    contributors_1.data_collection_date,
                                    contributors_1.cntrb_id AS canonical_id
                                   FROM augur_data.contributors contributors_1
                                  WHERE ((contributors_1.cntrb_canonical)::text = (contributors_1.cntrb_email)::text)
                                  ORDER BY contributors_1.cntrb_canonical) canonical_full_names ON (((canonical_full_names.canonical_email)::text = (contributors.cntrb_canonical)::text)))
                          GROUP BY commits.repo_id, canonical_full_names.canonical_email, canonical_full_names.canonical_id, commits.cmt_author_date, contributors.cntrb_full_name, contributors.cntrb_login
                        UNION ALL
                         SELECT message.cntrb_id AS id,
                            commit_comment_ref.created_at,
                            commits.repo_id,
                            'commit_comment'::text AS action,
                            contributors.cntrb_full_name AS full_name,
                            contributors.cntrb_login AS login
                           FROM augur_data.commit_comment_ref,
                            augur_data.commits,
                            ((augur_data.message
                             LEFT JOIN augur_data.contributors ON ((contributors.cntrb_id = message.cntrb_id)))
                             LEFT JOIN ( SELECT DISTINCT ON (contributors_1.cntrb_canonical) contributors_1.cntrb_full_name,
                                    contributors_1.cntrb_canonical AS canonical_email,
                                    contributors_1.data_collection_date,
                                    contributors_1.cntrb_id AS canonical_id
                                   FROM augur_data.contributors contributors_1
                                  WHERE ((contributors_1.cntrb_canonical)::text = (contributors_1.cntrb_email)::text)
                                  ORDER BY contributors_1.cntrb_canonical) canonical_full_names ON (((canonical_full_names.canonical_email)::text = (contributors.cntrb_canonical)::text)))
                          WHERE ((commits.cmt_id = commit_comment_ref.cmt_id) AND (commit_comment_ref.msg_id = message.msg_id))
                          GROUP BY message.cntrb_id, commits.repo_id, commit_comment_ref.created_at, contributors.cntrb_full_name, contributors.cntrb_login
                        UNION ALL
                         SELECT issue_events.cntrb_id AS id,
                            issue_events.created_at,
                            issues.repo_id,
                            'issue_closed'::text AS action,
                            contributors.cntrb_full_name AS full_name,
                            contributors.cntrb_login AS login
                           FROM augur_data.issues,
                            ((augur_data.issue_events
                             LEFT JOIN augur_data.contributors ON ((contributors.cntrb_id = issue_events.cntrb_id)))
                             LEFT JOIN ( SELECT DISTINCT ON (contributors_1.cntrb_canonical) contributors_1.cntrb_full_name,
                                    contributors_1.cntrb_canonical AS canonical_email,
                                    contributors_1.data_collection_date,
                                    contributors_1.cntrb_id AS canonical_id
                                   FROM augur_data.contributors contributors_1
                                  WHERE ((contributors_1.cntrb_canonical)::text = (contributors_1.cntrb_email)::text)
                                  ORDER BY contributors_1.cntrb_canonical) canonical_full_names ON (((canonical_full_names.canonical_email)::text = (contributors.cntrb_canonical)::text)))
                          WHERE ((issues.issue_id = issue_events.issue_id) AND (issues.pull_request IS NULL) AND (issue_events.cntrb_id IS NOT NULL) AND ((issue_events.action)::text = 'closed'::text))
                          GROUP BY issue_events.cntrb_id, issues.repo_id, issue_events.created_at, contributors.cntrb_full_name, contributors.cntrb_login
                        UNION ALL
                         SELECT pull_requests.pr_augur_contributor_id AS id,
                            pull_requests.pr_created_at AS created_at,
                            pull_requests.repo_id,
                            'open_pull_request'::text AS action,
                            contributors.cntrb_full_name AS full_name,
                            contributors.cntrb_login AS login
                           FROM ((augur_data.pull_requests
                             LEFT JOIN augur_data.contributors ON ((pull_requests.pr_augur_contributor_id = contributors.cntrb_id)))
                             LEFT JOIN ( SELECT DISTINCT ON (contributors_1.cntrb_canonical) contributors_1.cntrb_full_name,
                                    contributors_1.cntrb_canonical AS canonical_email,
                                    contributors_1.data_collection_date,
                                    contributors_1.cntrb_id AS canonical_id
                                   FROM augur_data.contributors contributors_1
                                  WHERE ((contributors_1.cntrb_canonical)::text = (contributors_1.cntrb_email)::text)
                                  ORDER BY contributors_1.cntrb_canonical) canonical_full_names ON (((canonical_full_names.canonical_email)::text = (contributors.cntrb_canonical)::text)))
                          GROUP BY pull_requests.pr_augur_contributor_id, pull_requests.repo_id, pull_requests.pr_created_at, contributors.cntrb_full_name, contributors.cntrb_login
                        UNION ALL
                         SELECT message.cntrb_id AS id,
                            message.msg_timestamp AS created_at,
                            pull_requests.repo_id,
                            'pull_request_comment'::text AS action,
                            contributors.cntrb_full_name AS full_name,
                            contributors.cntrb_login AS login
                           FROM augur_data.pull_requests,
                            augur_data.pull_request_message_ref,
                            ((augur_data.message
                             LEFT JOIN augur_data.contributors ON ((contributors.cntrb_id = message.cntrb_id)))
                             LEFT JOIN ( SELECT DISTINCT ON (contributors_1.cntrb_canonical) contributors_1.cntrb_full_name,
                                    contributors_1.cntrb_canonical AS canonical_email,
                                    contributors_1.data_collection_date,
                                    contributors_1.cntrb_id AS canonical_id
                                   FROM augur_data.contributors contributors_1
                                  WHERE ((contributors_1.cntrb_canonical)::text = (contributors_1.cntrb_email)::text)
                                  ORDER BY contributors_1.cntrb_canonical) canonical_full_names ON (((canonical_full_names.canonical_email)::text = (contributors.cntrb_canonical)::text)))
                          WHERE ((pull_request_message_ref.pull_request_id = pull_requests.pull_request_id) AND (pull_request_message_ref.msg_id = message.msg_id))
                          GROUP BY message.cntrb_id, pull_requests.repo_id, message.msg_timestamp, contributors.cntrb_full_name, contributors.cntrb_login
                        UNION ALL
                         SELECT issues.reporter_id AS id,
                            message.msg_timestamp AS created_at,
                            issues.repo_id,
                            'issue_comment'::text AS action,
                            contributors.cntrb_full_name AS full_name,
                            contributors.cntrb_login AS login
                           FROM augur_data.issues,
                            augur_data.issue_message_ref,
                            ((augur_data.message
                             LEFT JOIN augur_data.contributors ON ((contributors.cntrb_id = message.cntrb_id)))
                             LEFT JOIN ( SELECT DISTINCT ON (contributors_1.cntrb_canonical) contributors_1.cntrb_full_name,
                                    contributors_1.cntrb_canonical AS canonical_email,
                                    contributors_1.data_collection_date,
                                    contributors_1.cntrb_id AS canonical_id
                                   FROM augur_data.contributors contributors_1
                                  WHERE ((contributors_1.cntrb_canonical)::text = (contributors_1.cntrb_email)::text)
                                  ORDER BY contributors_1.cntrb_canonical) canonical_full_names ON (((canonical_full_names.canonical_email)::text = (contributors.cntrb_canonical)::text)))
                          WHERE ((issue_message_ref.msg_id = message.msg_id) AND (issues.issue_id = issue_message_ref.issue_id) AND (issues.pull_request_id = NULL::bigint))
                          GROUP BY issues.reporter_id, issues.repo_id, message.msg_timestamp, contributors.cntrb_full_name, contributors.cntrb_login) a,
                    augur_data.repo
                  WHERE ((a.id IS NOT NULL) AND (a.repo_id = repo.repo_id))
                  GROUP BY a.id, a.repo_id, a.action, a.created_at, repo.repo_name, a.full_name, a.login
                  ORDER BY a.id) b
          WHERE (b.rank = ANY (ARRAY[(1)::bigint, (2)::bigint, (3)::bigint, (4)::bigint, (5)::bigint, (6)::bigint, (7)::bigint]))) x"""

# ---------------------------------------------------------------------------
# View 9: explorer_pr_assignments (source: migration 26)
# ---------------------------------------------------------------------------
_EXPLORER_PR_ASSIGNMENTS = """\
SELECT
    pr.pull_request_id,
    pr.repo_id AS ID,
    pr.pr_created_at AS created,
    pr.pr_closed_at AS closed,
    pre.created_at AS assign_date,
    pre.ACTION AS assignment_action,
    pre.cntrb_id AS assignee,
    pre.node_id AS node_id
FROM
    (
      augur_data.pull_requests pr
      LEFT JOIN augur_data.pull_request_events pre ON (
        (
          ( pr.pull_request_id = pre.pull_request_id )
          AND (
            ( pre.ACTION ) :: TEXT = ANY ( ARRAY [ ( 'unassigned' :: CHARACTER VARYING ) :: TEXT, ( 'assigned' :: CHARACTER VARYING ) :: TEXT ] )
          )
        )
      )
    )"""

# ---------------------------------------------------------------------------
# View 10: explorer_pr_response (source: migration 26)
# ---------------------------------------------------------------------------
_EXPLORER_PR_RESPONSE = """\
SELECT pr.pull_request_id,
    pr.repo_id AS id,
    pr.pr_augur_contributor_id AS cntrb_id,
    m.msg_timestamp,
    m.msg_cntrb_id,
    pr.pr_created_at,
    pr.pr_closed_at
  FROM (augur_data.pull_requests pr
    LEFT JOIN ( SELECT prr.pull_request_id,
            m_1.msg_timestamp,
            m_1.cntrb_id AS msg_cntrb_id
          FROM augur_data.pull_request_review_message_ref prrmr,
            augur_data.pull_requests pr_1,
            augur_data.message m_1,
            augur_data.pull_request_reviews prr
          WHERE ((prrmr.pr_review_id = prr.pr_review_id) AND (prrmr.msg_id = m_1.msg_id) AND (prr.pull_request_id = pr_1.pull_request_id))
        UNION
        SELECT prmr.pull_request_id,
            m_1.msg_timestamp,
            m_1.cntrb_id AS msg_cntrb_id
          FROM augur_data.pull_request_message_ref prmr,
            augur_data.pull_requests pr_1,
            augur_data.message m_1
          WHERE ((prmr.pull_request_id = pr_1.pull_request_id) AND (prmr.msg_id = m_1.msg_id))) m ON ((m.pull_request_id = pr.pull_request_id)))"""

# ---------------------------------------------------------------------------
# View 11: explorer_user_repos (source: migration 26)
# ---------------------------------------------------------------------------
_EXPLORER_USER_REPOS = """\
SELECT a.login_name,
    a.user_id,
    b.group_id,
    c.repo_id
  FROM augur_operations.users a,
    augur_operations.user_groups b,
    augur_operations.user_repos c
  WHERE ((a.user_id = b.user_id) AND (b.group_id = c.group_id))
  ORDER BY a.user_id"""

# ---------------------------------------------------------------------------
# View 12: explorer_pr_response_times (source: migration 26)
# ---------------------------------------------------------------------------
_EXPLORER_PR_RESPONSE_TIMES = """\
SELECT repo.repo_id,
    pull_requests.pr_src_id,
    repo.repo_name,
    pull_requests.pr_src_author_association,
    repo_groups.rg_name AS repo_group,
    pull_requests.pr_src_state,
    pull_requests.pr_merged_at,
    pull_requests.pr_created_at,
    pull_requests.pr_closed_at,
    date_part('year'::text, (pull_requests.pr_created_at)::date) AS created_year,
    date_part('month'::text, (pull_requests.pr_created_at)::date) AS created_month,
    date_part('year'::text, (pull_requests.pr_closed_at)::date) AS closed_year,
    date_part('month'::text, (pull_requests.pr_closed_at)::date) AS closed_month,
    base_labels.pr_src_meta_label,
    base_labels.pr_head_or_base,
    ((EXTRACT(epoch FROM pull_requests.pr_closed_at) - EXTRACT(epoch FROM pull_requests.pr_created_at)) / (3600)::numeric) AS hours_to_close,
    ((EXTRACT(epoch FROM pull_requests.pr_closed_at) - EXTRACT(epoch FROM pull_requests.pr_created_at)) / (86400)::numeric) AS days_to_close,
    ((EXTRACT(epoch FROM response_times.first_response_time) - EXTRACT(epoch FROM pull_requests.pr_created_at)) / (3600)::numeric) AS hours_to_first_response,
    ((EXTRACT(epoch FROM response_times.first_response_time) - EXTRACT(epoch FROM pull_requests.pr_created_at)) / (86400)::numeric) AS days_to_first_response,
    ((EXTRACT(epoch FROM response_times.last_response_time) - EXTRACT(epoch FROM pull_requests.pr_created_at)) / (3600)::numeric) AS hours_to_last_response,
    ((EXTRACT(epoch FROM response_times.last_response_time) - EXTRACT(epoch FROM pull_requests.pr_created_at)) / (86400)::numeric) AS days_to_last_response,
    response_times.first_response_time,
    response_times.last_response_time,
    response_times.average_time_between_responses,
    response_times.assigned_count,
    response_times.review_requested_count,
    response_times.labeled_count,
    response_times.subscribed_count,
    response_times.mentioned_count,
    response_times.referenced_count,
    response_times.closed_count,
    response_times.head_ref_force_pushed_count,
    response_times.merged_count,
    response_times.milestoned_count,
    response_times.unlabeled_count,
    response_times.head_ref_deleted_count,
    response_times.comment_count,
    master_merged_counts.lines_added,
    master_merged_counts.lines_removed,
    all_commit_counts.commit_count,
    master_merged_counts.file_count
  FROM augur_data.repo,
    augur_data.repo_groups,
    ((((augur_data.pull_requests
    LEFT JOIN ( SELECT pull_requests_1.pull_request_id,
            count(*) FILTER (WHERE ((pull_request_events.action)::text = 'assigned'::text)) AS assigned_count,
            count(*) FILTER (WHERE ((pull_request_events.action)::text = 'review_requested'::text)) AS review_requested_count,
            count(*) FILTER (WHERE ((pull_request_events.action)::text = 'labeled'::text)) AS labeled_count,
            count(*) FILTER (WHERE ((pull_request_events.action)::text = 'unlabeled'::text)) AS unlabeled_count,
            count(*) FILTER (WHERE ((pull_request_events.action)::text = 'subscribed'::text)) AS subscribed_count,
            count(*) FILTER (WHERE ((pull_request_events.action)::text = 'mentioned'::text)) AS mentioned_count,
            count(*) FILTER (WHERE ((pull_request_events.action)::text = 'referenced'::text)) AS referenced_count,
            count(*) FILTER (WHERE ((pull_request_events.action)::text = 'closed'::text)) AS closed_count,
            count(*) FILTER (WHERE ((pull_request_events.action)::text = 'head_ref_force_pushed'::text)) AS head_ref_force_pushed_count,
            count(*) FILTER (WHERE ((pull_request_events.action)::text = 'head_ref_deleted'::text)) AS head_ref_deleted_count,
            count(*) FILTER (WHERE ((pull_request_events.action)::text = 'milestoned'::text)) AS milestoned_count,
            count(*) FILTER (WHERE ((pull_request_events.action)::text = 'merged'::text)) AS merged_count,
            min(message.msg_timestamp) AS first_response_time,
            count(DISTINCT message.msg_timestamp) AS comment_count,
            max(message.msg_timestamp) AS last_response_time,
            ((max(message.msg_timestamp) - min(message.msg_timestamp)) / (count(DISTINCT message.msg_timestamp))::double precision) AS average_time_between_responses
          FROM augur_data.pull_request_events,
            augur_data.pull_requests pull_requests_1,
            augur_data.repo repo_1,
            augur_data.pull_request_message_ref,
            augur_data.message
          WHERE ((repo_1.repo_id = pull_requests_1.repo_id) AND (pull_requests_1.pull_request_id = pull_request_events.pull_request_id) AND (pull_requests_1.pull_request_id = pull_request_message_ref.pull_request_id) AND (pull_request_message_ref.msg_id = message.msg_id))
          GROUP BY pull_requests_1.pull_request_id) response_times ON ((pull_requests.pull_request_id = response_times.pull_request_id)))
    LEFT JOIN ( SELECT pull_request_commits.pull_request_id,
            count(DISTINCT pull_request_commits.pr_cmt_sha) AS commit_count
          FROM augur_data.pull_request_commits,
            augur_data.pull_requests pull_requests_1,
            augur_data.pull_request_meta
          WHERE ((pull_requests_1.pull_request_id = pull_request_commits.pull_request_id) AND (pull_requests_1.pull_request_id = pull_request_meta.pull_request_id) AND ((pull_request_commits.pr_cmt_sha)::text <> (pull_requests_1.pr_merge_commit_sha)::text) AND ((pull_request_commits.pr_cmt_sha)::text <> (pull_request_meta.pr_sha)::text))
          GROUP BY pull_request_commits.pull_request_id) all_commit_counts ON ((pull_requests.pull_request_id = all_commit_counts.pull_request_id)))
    LEFT JOIN ( SELECT max(pull_request_meta.pr_repo_meta_id) AS max,
            pull_request_meta.pull_request_id,
            pull_request_meta.pr_head_or_base,
            pull_request_meta.pr_src_meta_label
          FROM augur_data.pull_requests pull_requests_1,
            augur_data.pull_request_meta
          WHERE ((pull_requests_1.pull_request_id = pull_request_meta.pull_request_id) AND ((pull_request_meta.pr_head_or_base)::text = 'base'::text))
          GROUP BY pull_request_meta.pull_request_id, pull_request_meta.pr_head_or_base, pull_request_meta.pr_src_meta_label) base_labels ON ((base_labels.pull_request_id = all_commit_counts.pull_request_id)))
    LEFT JOIN ( SELECT sum(commits.cmt_added) AS lines_added,
            sum(commits.cmt_removed) AS lines_removed,
            pull_request_commits.pull_request_id,
            count(DISTINCT commits.cmt_filename) AS file_count
          FROM augur_data.pull_request_commits,
            augur_data.commits,
            augur_data.pull_requests pull_requests_1,
            augur_data.pull_request_meta
          WHERE (((commits.cmt_commit_hash)::text = (pull_request_commits.pr_cmt_sha)::text) AND (pull_requests_1.pull_request_id = pull_request_commits.pull_request_id) AND (pull_requests_1.pull_request_id = pull_request_meta.pull_request_id) AND (commits.repo_id = pull_requests_1.repo_id) AND ((commits.cmt_commit_hash)::text <> (pull_requests_1.pr_merge_commit_sha)::text) AND ((commits.cmt_commit_hash)::text <> (pull_request_meta.pr_sha)::text))
          GROUP BY pull_request_commits.pull_request_id) master_merged_counts ON ((base_labels.pull_request_id = master_merged_counts.pull_request_id)))
  WHERE ((repo.repo_group_id = repo_groups.repo_group_id) AND (repo.repo_id = pull_requests.repo_id))
  ORDER BY response_times.merged_count DESC"""

# ---------------------------------------------------------------------------
# View 13: explorer_issue_assignments (source: migration 26)
# ---------------------------------------------------------------------------
_EXPLORER_ISSUE_ASSIGNMENTS = """\
SELECT
    i.issue_id,
    i.repo_id AS ID,
    i.created_at AS created,
    i.closed_at AS closed,
    ie.created_at AS assign_date,
    ie.ACTION AS assignment_action,
    ie.cntrb_id AS assignee,
    ie.node_id as node_id
FROM
    (
      augur_data.issues i
      LEFT JOIN augur_data.issue_events ie ON (
        (
          ( i.issue_id = ie.issue_id )
          AND (
            ( ie.ACTION ) :: TEXT = ANY ( ARRAY [ ( 'unassigned' :: CHARACTER VARYING ) :: TEXT, ( 'assigned' :: CHARACTER VARYING ) :: TEXT ] )
          )
        )
      )
    )"""

# ---------------------------------------------------------------------------
# View 14: explorer_repo_languages (source: migration 28)
# ---------------------------------------------------------------------------
_EXPLORER_REPO_LANGUAGES = """\
SELECT e.repo_id,
    repo.repo_git,
    repo.repo_name,
    e.programming_language,
    e.code_lines,
    e.files
  FROM augur_data.repo,
    ( SELECT d.repo_id,
            d.programming_language,
            sum(d.code_lines) AS code_lines,
            (count(*))::integer AS files
          FROM ( SELECT repo_labor.repo_id,
                    repo_labor.programming_language,
                    repo_labor.code_lines
                  FROM augur_data.repo_labor,
                    ( SELECT repo_labor_1.repo_id,
                            max(repo_labor_1.data_collection_date) AS last_collected
                          FROM augur_data.repo_labor repo_labor_1
                          GROUP BY repo_labor_1.repo_id) recent
                  WHERE ((repo_labor.repo_id = recent.repo_id) AND (repo_labor.data_collection_date > (recent.last_collected - ((5)::double precision * '00:01:00'::interval))))) d
          GROUP BY d.repo_id, d.programming_language) e
  WHERE (repo.repo_id = e.repo_id)
  ORDER BY e.repo_id"""

# ---------------------------------------------------------------------------
# View 15: explorer_cntrb_per_file (new - from 8Knot PR #1086)
#   Uses text cast instead of varchar(15) because BigInt can be 19 digits.
# ---------------------------------------------------------------------------
_EXPLORER_CNTRB_PER_FILE = """\
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
GROUP BY prf.pr_file_path, pr.repo_id"""

# ---------------------------------------------------------------------------
# View 16: explorer_pr_files (new - from 8Knot PR #1086)
#   DISTINCT added to protect unique index from dirty data.
# ---------------------------------------------------------------------------
_EXPLORER_PR_FILES = """\
SELECT DISTINCT
    prf.pr_file_path AS file_path,
    pr.pull_request_id AS pull_request_id,
    pr.repo_id AS repo_id
FROM augur_data.pull_requests pr
INNER JOIN augur_data.pull_request_files prf
    ON pr.pull_request_id = prf.pull_request_id"""

# ---------------------------------------------------------------------------
# View 17: explorer_repo_files (new - from 8Knot PR #1086)
#   Uses repo_id (not id) per MoralCode's review feedback.
# ---------------------------------------------------------------------------
_EXPLORER_REPO_FILES = """\
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
)"""


# ============================================================================
# Registry: single source of truth for all materialized views
# ============================================================================

MATERIALIZED_VIEWS = [
    # --- Views 1-5: from migration 4, indexes from migration 25 ---
    {
        "name": "api_get_all_repo_prs",
        "schema": "augur_data",
        "sql": _API_GET_ALL_REPO_PRS,
        "unique_index_columns": ["repo_id"],
    },
    {
        "name": "explorer_entry_list",
        "schema": "augur_data",
        "sql": _EXPLORER_ENTRY_LIST,
        "unique_index_columns": ["repo_id"],
    },
    {
        "name": "explorer_commits_and_committers_daily_count",
        "schema": "augur_data",
        "sql": _EXPLORER_COMMITS_AND_COMMITTERS_DAILY_COUNT,
        "unique_index_columns": ["repo_id", "cmt_committer_date"],
    },
    {
        "name": "api_get_all_repos_commits",
        "schema": "augur_data",
        "sql": _API_GET_ALL_REPOS_COMMITS,
        "unique_index_columns": ["repo_id"],
    },
    {
        "name": "api_get_all_repos_issues",
        "schema": "augur_data",
        "sql": _API_GET_ALL_REPOS_ISSUES,
        "unique_index_columns": ["repo_id"],
    },
    # --- Views 6-8: from migration 25, recreated ---
    {
        "name": "augur_new_contributors",
        "schema": "augur_data",
        "sql": _AUGUR_NEW_CONTRIBUTORS,
        "unique_index_columns": ["cntrb_id", "created_at", "repo_id", "repo_name", "login", "rank"],
    },
    {
        "name": "explorer_contributor_actions",
        "schema": "augur_data",
        "sql": _EXPLORER_CONTRIBUTOR_ACTIONS,
        "unique_index_columns": ["cntrb_id", "created_at", "repo_id", "action", "repo_name", "login", "rank"],
    },
    {
        "name": "explorer_new_contributors",
        "schema": "augur_data",
        "sql": _EXPLORER_NEW_CONTRIBUTORS,
        "unique_index_columns": ["cntrb_id", "created_at", "month", "year", "repo_id", "full_name", "repo_name", "login", "rank"],
    },
    # --- Views 9-13: from migration 26 ---
    {
        "name": "explorer_pr_assignments",
        "schema": "augur_data",
        "sql": _EXPLORER_PR_ASSIGNMENTS,
        "unique_index_columns": ["pull_request_id", "id", "node_id"],
    },
    {
        "name": "explorer_pr_response",
        "schema": "augur_data",
        "sql": _EXPLORER_PR_RESPONSE,
        "unique_index_columns": ["pull_request_id", "id", "cntrb_id", "msg_cntrb_id", "msg_timestamp"],
    },
    {
        "name": "explorer_user_repos",
        "schema": "augur_data",
        "sql": _EXPLORER_USER_REPOS,
        "unique_index_columns": ["login_name", "user_id", "group_id", "repo_id"],
    },
    {
        "name": "explorer_pr_response_times",
        "schema": "augur_data",
        "sql": _EXPLORER_PR_RESPONSE_TIMES,
        "unique_index_columns": ["repo_id", "pr_src_id", "pr_src_meta_label"],
    },
    {
        "name": "explorer_issue_assignments",
        "schema": "augur_data",
        "sql": _EXPLORER_ISSUE_ASSIGNMENTS,
        "unique_index_columns": ["issue_id", "id", "node_id"],
    },
    # --- View 14: from migration 28 ---
    {
        "name": "explorer_repo_languages",
        "schema": "augur_data",
        "sql": _EXPLORER_REPO_LANGUAGES,
        "unique_index_columns": ["repo_id", "programming_language"],
    },
    # --- Views 15-17: new heatmap views (from 8Knot PR #1086) ---
    {
        "name": "explorer_cntrb_per_file",
        "schema": "augur_data",
        "sql": _EXPLORER_CNTRB_PER_FILE,
        "unique_index_columns": ["repo_id", "file_path"],
    },
    {
        "name": "explorer_pr_files",
        "schema": "augur_data",
        "sql": _EXPLORER_PR_FILES,
        "unique_index_columns": ["file_path", "pull_request_id", "repo_id"],
    },
    {
        "name": "explorer_repo_files",
        "schema": "augur_data",
        "sql": _EXPLORER_REPO_FILES,
        "unique_index_columns": ["repo_id", "file_path", "file_name", "rl_analysis_date"],
    },
]


def get_refresh_sql(view, concurrently=True):
    """Construct a REFRESH MATERIALIZED VIEW statement.

    Args:
        view: A dict from MATERIALIZED_VIEWS.
        concurrently: If True, use CONCURRENTLY (requires a unique index
            and the view to have been populated at least once).

    Returns:
        SQL string ready to be wrapped in sqlalchemy.sql.text().
    """
    mode = "CONCURRENTLY " if concurrently else ""
    return (
        f"REFRESH MATERIALIZED VIEW {mode}"
        f"{view['schema']}.{view['name']} WITH DATA; COMMIT;"
    )
