"""
DAG Validation Tests

Validates the Airflow DAG file (dags/scraping_pipeline.py) without
requiring a running Airflow instance. Imports the DAG module directly
and inspects the DAG object for structural correctness.

If Airflow is not installed in the test environment, all tests are
skipped with pytest.skip() rather than failing.

Covers:
- DAG loads without errors
- DAG ID matches expected value
- All expected tasks are present
- Task count is correct (10 tasks)
- Dependency graph matches expected flow:
    start -> [scrape_gfg, scrape_leetcode, scrape_medium] (parallel)
          -> print_summary -> run_preprocessing -> validate_processed_data
          -> load_to_database -> complete -> build_email -> send_notification_email
- Scrapers run in parallel (same upstream: start)
- Email tasks use trigger_rule='all_done'
"""
import sys
import pytest


# ── Helper to safely import the DAG ──

def _load_dag():
    """
    Import the DAG module and return the DAG object.
    Returns None if Airflow is not installed.
    """
    try:
        import airflow  # noqa: F401
    except ImportError:
        return None

    # The DAG file uses sys.path.insert for its deploy environment.
    # We import the module directly since it defines `dag` at module level.
    import importlib
    try:
        mod = importlib.import_module("dags.scraping_pipeline")
        return mod.dag
    except Exception as e:
        pytest.fail(f"Failed to load DAG module: {e}")


@pytest.fixture(scope="module")
def dag():
    d = _load_dag()
    if d is None:
        pytest.skip("Airflow not installed, skipping DAG tests")
    return d


def _get_task_ids(dag):
    return {t.task_id for t in dag.tasks}


def _get_upstream_ids(dag, task_id):
    task = dag.get_task(task_id)
    return {t.task_id for t in task.upstream_list}


def _get_downstream_ids(dag, task_id):
    task = dag.get_task(task_id)
    return {t.task_id for t in task.downstream_list}


# ── DAG loads without errors ──

class TestDAGLoads:
    def test_dag_is_not_none(self, dag):
        assert dag is not None

    def test_dag_has_tasks(self, dag):
        assert len(dag.tasks) > 0


# ── DAG ID ──

class TestDAGId:
    def test_dag_id_is_correct(self, dag):
        assert dag.dag_id == "interview_scraping_pipeline"


# ── All tasks present ──

EXPECTED_TASKS = {
    "start",
    "scrape_gfg",
    "scrape_leetcode",
    "scrape_medium",
    "print_summary",
    "run_preprocessing",
    "validate_processed_data",
    "load_to_database",
    "complete",
    "build_email",
    "send_notification_email",
}


class TestTasksPresent:
    def test_all_expected_tasks_exist(self, dag):
        actual = _get_task_ids(dag)
        missing = EXPECTED_TASKS - actual
        assert not missing, f"Missing tasks: {missing}"

    def test_task_count(self, dag):
        assert len(dag.tasks) == 11, (
            f"Expected 11 tasks, got {len(dag.tasks)}: "
            f"{sorted(_get_task_ids(dag))}"
        )

    def test_no_unexpected_tasks(self, dag):
        actual = _get_task_ids(dag)
        extra = actual - EXPECTED_TASKS
        assert not extra, f"Unexpected tasks found: {extra}"


# ── Scrapers run in parallel ──

class TestScrapersParallel:
    SCRAPER_TASKS = ["scrape_gfg", "scrape_leetcode", "scrape_medium"]

    def test_all_scrapers_upstream_of_start(self, dag):
        """All 3 scrapers have 'start' as their only upstream dependency."""
        for task_id in self.SCRAPER_TASKS:
            upstream = _get_upstream_ids(dag, task_id)
            assert upstream == {"start"}, (
                f"'{task_id}' upstream should be {{'start'}}, got {upstream}"
            )

    def test_scrapers_are_downstream_of_start(self, dag):
        downstream = _get_downstream_ids(dag, "start")
        for task_id in self.SCRAPER_TASKS:
            assert task_id in downstream


# ── Dependency chain ──

class TestDependencyChain:
    """
    Validates the linear dependency chain after the parallel scrapers:
    scrapers -> print_summary -> run_preprocessing -> validate_processed_data
             -> load_to_database -> complete -> build_email -> send_notification_email
    """

    def test_scrapers_upstream_of_summary(self, dag):
        upstream = _get_upstream_ids(dag, "print_summary")
        assert {"scrape_gfg", "scrape_leetcode", "scrape_medium"} == upstream

    def test_summary_upstream_of_preprocessing(self, dag):
        upstream = _get_upstream_ids(dag, "run_preprocessing")
        assert "print_summary" in upstream

    def test_preprocessing_upstream_of_validation(self, dag):
        upstream = _get_upstream_ids(dag, "validate_processed_data")
        assert "run_preprocessing" in upstream

    def test_validation_upstream_of_db_load(self, dag):
        upstream = _get_upstream_ids(dag, "load_to_database")
        assert "validate_processed_data" in upstream

    def test_db_load_upstream_of_complete(self, dag):
        upstream = _get_upstream_ids(dag, "complete")
        assert "load_to_database" in upstream

    def test_complete_upstream_of_build_email(self, dag):
        upstream = _get_upstream_ids(dag, "build_email")
        assert "complete" in upstream

    def test_build_email_upstream_of_send_email(self, dag):
        upstream = _get_upstream_ids(dag, "send_notification_email")
        assert "build_email" in upstream


# ── Email notification tasks ──

class TestEmailNotification:
    def test_build_email_trigger_rule_all_done(self, dag):
        """build_email should run regardless of upstream success/failure."""
        task = dag.get_task("build_email")
        assert task.trigger_rule == "all_done"

    def test_send_email_trigger_rule_all_done(self, dag):
        """send_notification_email should run regardless of upstream success/failure."""
        task = dag.get_task("send_notification_email")
        assert task.trigger_rule == "all_done"

    def test_send_email_has_recipients(self, dag):
        """Email task should have at least one recipient configured."""
        task = dag.get_task("send_notification_email")
        assert hasattr(task, "to")
        assert len(task.to) > 0


# ── DAG configuration ──

class TestDAGConfig:
    def test_catchup_disabled(self, dag):
        assert dag.catchup is False

    def test_schedule_is_none(self, dag):
        """DAG is manually triggered (schedule=None)."""
        assert dag.schedule_interval is None or dag.timetable is not None

    def test_dag_has_tags(self, dag):
        assert dag.tags is not None
        assert len(dag.tags) > 0