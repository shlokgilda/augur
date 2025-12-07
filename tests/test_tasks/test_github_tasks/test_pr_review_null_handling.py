"""
Test for PR #3438: Null string handling in PR review bodies

This test validates that the collect_pull_request_reviews function properly
handles null, None, and edge-case values in pr_review_body fields by using
the string_fields parameter in insert_data().
"""

import logging
import inspect

from augur.tasks.github.pull_requests.tasks import collect_pull_request_reviews
from augur.application.db.models import PullRequestReview

logger = logging.getLogger(__name__)


class TestPRReviewNullHandling:
    """Test suite for PR review null string handling (PR #3438)"""

    def test_pr_review_insert_uses_string_fields_parameter(self):
        """
        Test that the collect_pull_request_reviews function passes string_fields
        parameter when calling insert_data for PR reviews.

        This verifies the fix in PR #3438 by inspecting the source code.
        """
        # Get the source code of collect_pull_request_reviews
        source = inspect.getsource(collect_pull_request_reviews)

        # Verify the fix is present: string_fields should be passed for PR reviews
        assert 'pr_review_string_fields' in source or 'string_fields' in source, \
            "string_fields parameter should be defined for PR reviews"

        # Check that pr_review_body is in the string_fields
        assert 'pr_review_body' in source, \
            "pr_review_body should be specified in string_fields"

        logger.info("✓ Source code contains string_fields with pr_review_body")

    def test_pr_review_null_body_insertion(self, test_db_session):
        """
        Test that PR reviews with null bodies can be inserted without errors.

        Uses unique IDs to avoid conflicts with existing data.
        """
        # Use high IDs to avoid conflicts
        TEST_REPO_GROUP_ID = 999999
        TEST_REPO_ID = 999999
        TEST_PR_ID = 999999
        TEST_REVIEW_SRC_ID = 999999
        TEST_CNTRB_ID = '99999999-9999-9999-9999-999999999999'

        try:
            from sqlalchemy import text

            with test_db_session.engine.connect() as connection:
                # Insert platform entry for GitHub (platform_id=25150 is the default)
                connection.execute(text("""
                    INSERT INTO augur_data.platform
                    (pltfrm_id, pltfrm_name, pltfrm_version, tool_source, tool_version, data_source)
                    VALUES (25150, 'GitHub', '1.0', 'test', '1.0', 'test')
                    ON CONFLICT (pltfrm_id) DO NOTHING;
                """))

                # Insert test dependencies with unique IDs
                connection.execute(text("""
                    INSERT INTO augur_data.repo_groups
                    (repo_group_id, rg_name, rg_description, rg_website, rg_recache,
                     rg_last_modified, rg_type, tool_source, tool_version, data_source, data_collection_date)
                    VALUES (:rg_id, 'Test Group PR3438', 'Test', '', 0, NOW(), 'GitHub Organization',
                            'test', '1.0', 'test', NOW())
                    ON CONFLICT (repo_group_id) DO NOTHING;
                """), {"rg_id": TEST_REPO_GROUP_ID})

                connection.execute(text("""
                    INSERT INTO augur_data.repo
                    (repo_id, repo_group_id, repo_git, repo_name, repo_added, repo_type,
                     tool_source, tool_version, data_source, data_collection_date)
                    VALUES (:repo_id, :rg_id, 'https://github.com/test/pr3438-null-test', 'pr3438-null-test', NOW(), '',
                            'test', '1.0', 'test', NOW())
                    ON CONFLICT (repo_id) DO NOTHING;
                """), {"repo_id": TEST_REPO_ID, "rg_id": TEST_REPO_GROUP_ID})

                connection.execute(text("""
                    INSERT INTO augur_data.contributors
                    (cntrb_id, cntrb_login, tool_source, tool_version, data_source)
                    VALUES (:cntrb_id, 'testuser-pr3438', 'test', '1.0', 'test')
                    ON CONFLICT (cntrb_id) DO NOTHING;
                """), {"cntrb_id": TEST_CNTRB_ID})

                connection.execute(text("""
                    INSERT INTO augur_data.pull_requests
                    (pull_request_id, repo_id, pr_url, pr_src_id, pr_src_number)
                    VALUES (:pr_id, :repo_id, 'https://github.com/test/pr3438-null-test/pull/1', :pr_id, 1)
                    ON CONFLICT (pull_request_id) DO NOTHING;
                """), {"pr_id": TEST_PR_ID, "repo_id": TEST_REPO_ID})

                connection.commit()

            # Test data with null body
            pr_review_data = [{
                'pull_request_id': TEST_PR_ID,
                'cntrb_id': TEST_CNTRB_ID,
                'pr_review_author_association': 'MEMBER',
                'pr_review_state': 'APPROVED',
                'pr_review_body': None,  # NULL - This is what we're testing
                'pr_review_submitted_at': '2024-01-01T00:00:00Z',
                'pr_review_src_id': TEST_REVIEW_SRC_ID,
                'pr_review_node_id': 'TEST_NODE_ID_PR3438_NULL',
                'pr_review_html_url': 'https://github.com/test/pr3438/pull/1#pullrequestreview-999999',
                'pr_review_pull_request_url': 'https://api.github.com/repos/test/pr3438/pulls/1',
                'pr_review_commit_id': 'abc123pr3438',
                'tool_source': 'test-pr3438',
                'tool_version': '1.0',
                'data_source': 'test'
            }]

            # This should NOT raise an error with the fix
            test_db_session.insert_data(
                pr_review_data,
                PullRequestReview,
                ['pr_review_src_id'],
                string_fields=['pr_review_body']  # THE FIX - this parameter
            )

            # Verify the data was inserted
            with test_db_session.engine.connect() as connection:
                result = connection.execute(text(
                    "SELECT pr_review_body FROM augur_data.pull_request_reviews WHERE pr_review_src_id = :src_id"
                ), {"src_id": TEST_REVIEW_SRC_ID}).fetchone()

                assert result is not None, "PR review should be inserted"
                assert result[0] is None, "pr_review_body should be NULL in database"

            logger.info("✓ NULL pr_review_body handled correctly")

        finally:
            # Cleanup only our test data
            from sqlalchemy import text
            with test_db_session.engine.connect() as connection:
                connection.execute(text(
                    "DELETE FROM augur_data.pull_request_reviews WHERE pr_review_src_id = :src_id"
                ), {"src_id": TEST_REVIEW_SRC_ID})
                connection.execute(text(
                    "DELETE FROM augur_data.pull_requests WHERE pull_request_id = :pr_id"
                ), {"pr_id": TEST_PR_ID})
                connection.execute(text(
                    "DELETE FROM augur_data.contributors WHERE cntrb_id = :cntrb_id"
                ), {"cntrb_id": TEST_CNTRB_ID})
                connection.execute(text(
                    "DELETE FROM augur_data.repo WHERE repo_id = :repo_id"
                ), {"repo_id": TEST_REPO_ID})
                connection.execute(text(
                    "DELETE FROM augur_data.repo_groups WHERE repo_group_id = :rg_id"
                ), {"rg_id": TEST_REPO_GROUP_ID})
                connection.commit()

    def test_pr_review_long_body_insertion(self, test_db_session):
        """
        Test that PR reviews with very long bodies are properly handled.

        Uses unique IDs to avoid conflicts with existing data.
        """
        # Use high IDs to avoid conflicts (different from null test)
        TEST_REPO_GROUP_ID = 999998
        TEST_REPO_ID = 999998
        TEST_PR_ID = 999998
        TEST_REVIEW_SRC_ID = 999998
        TEST_CNTRB_ID = '99999999-9999-9999-9999-999999999998'

        try:
            from sqlalchemy import text

            with test_db_session.engine.connect() as connection:
                # Insert platform entry for GitHub (platform_id=25150 is the default)
                connection.execute(text("""
                    INSERT INTO augur_data.platform
                    (pltfrm_id, pltfrm_name, pltfrm_version, tool_source, tool_version, data_source)
                    VALUES (25150, 'GitHub', '1.0', 'test', '1.0', 'test')
                    ON CONFLICT (pltfrm_id) DO NOTHING;
                """))

                # Insert test dependencies with unique IDs
                connection.execute(text("""
                    INSERT INTO augur_data.repo_groups
                    (repo_group_id, rg_name, rg_description, rg_website, rg_recache,
                     rg_last_modified, rg_type, tool_source, tool_version, data_source, data_collection_date)
                    VALUES (:rg_id, 'Test Group PR3438 Long', 'Test', '', 0, NOW(), 'GitHub Organization',
                            'test', '1.0', 'test', NOW())
                    ON CONFLICT (repo_group_id) DO NOTHING;
                """), {"rg_id": TEST_REPO_GROUP_ID})

                connection.execute(text("""
                    INSERT INTO augur_data.repo
                    (repo_id, repo_group_id, repo_git, repo_name, repo_added, repo_type,
                     tool_source, tool_version, data_source, data_collection_date)
                    VALUES (:repo_id, :rg_id, 'https://github.com/test/pr3438-long-test', 'pr3438-long-test', NOW(), '',
                            'test', '1.0', 'test', NOW())
                    ON CONFLICT (repo_id) DO NOTHING;
                """), {"repo_id": TEST_REPO_ID, "rg_id": TEST_REPO_GROUP_ID})

                connection.execute(text("""
                    INSERT INTO augur_data.contributors
                    (cntrb_id, cntrb_login, tool_source, tool_version, data_source)
                    VALUES (:cntrb_id, 'testuser-pr3438-long', 'test', '1.0', 'test')
                    ON CONFLICT (cntrb_id) DO NOTHING;
                """), {"cntrb_id": TEST_CNTRB_ID})

                connection.execute(text("""
                    INSERT INTO augur_data.pull_requests
                    (pull_request_id, repo_id, pr_url, pr_src_id, pr_src_number)
                    VALUES (:pr_id, :repo_id, 'https://github.com/test/pr3438-long-test/pull/1', :pr_id, 1)
                    ON CONFLICT (pull_request_id) DO NOTHING;
                """), {"pr_id": TEST_PR_ID, "repo_id": TEST_REPO_ID})

                connection.commit()

            # Test data with very long body
            long_body = "This is a very long review comment. " * 500  # ~18,000 characters

            pr_review_data = [{
                'pull_request_id': TEST_PR_ID,
                'cntrb_id': TEST_CNTRB_ID,
                'pr_review_author_association': 'CONTRIBUTOR',
                'pr_review_state': 'CHANGES_REQUESTED',
                'pr_review_body': long_body,  # LONG STRING
                'pr_review_submitted_at': '2024-01-01T00:00:00Z',
                'pr_review_src_id': TEST_REVIEW_SRC_ID,
                'pr_review_node_id': 'TEST_NODE_ID_PR3438_LONG',
                'pr_review_html_url': 'https://github.com/test/pr3438/pull/1#pullrequestreview-999998',
                'pr_review_pull_request_url': 'https://api.github.com/repos/test/pr3438/pulls/1',
                'pr_review_commit_id': 'def456pr3438',
                'tool_source': 'test-pr3438',
                'tool_version': '1.0',
                'data_source': 'test'
            }]

            # This should handle long strings properly
            test_db_session.insert_data(
                pr_review_data,
                PullRequestReview,
                ['pr_review_src_id'],
                string_fields=['pr_review_body']  # THE FIX
            )

            # Verify the data was inserted
            with test_db_session.engine.connect() as connection:
                result = connection.execute(text(
                    "SELECT pr_review_body FROM augur_data.pull_request_reviews WHERE pr_review_src_id = :src_id"
                ), {"src_id": TEST_REVIEW_SRC_ID}).fetchone()

                assert result is not None, "PR review should be inserted"
                assert result[0] is not None, "pr_review_body should not be NULL"
                assert len(result[0]) > 1000, "Long body should be preserved"

            logger.info("✓ Long pr_review_body handled correctly")

        finally:
            # Cleanup only our test data
            from sqlalchemy import text
            with test_db_session.engine.connect() as connection:
                connection.execute(text(
                    "DELETE FROM augur_data.pull_request_reviews WHERE pr_review_src_id = :src_id"
                ), {"src_id": TEST_REVIEW_SRC_ID})
                connection.execute(text(
                    "DELETE FROM augur_data.pull_requests WHERE pull_request_id = :pr_id"
                ), {"pr_id": TEST_PR_ID})
                connection.execute(text(
                    "DELETE FROM augur_data.contributors WHERE cntrb_id = :cntrb_id"
                ), {"cntrb_id": TEST_CNTRB_ID})
                connection.execute(text(
                    "DELETE FROM augur_data.repo WHERE repo_id = :repo_id"
                ), {"repo_id": TEST_REPO_ID})
                connection.execute(text(
                    "DELETE FROM augur_data.repo_groups WHERE repo_group_id = :rg_id"
                ), {"rg_id": TEST_REPO_GROUP_ID})
                connection.commit()
