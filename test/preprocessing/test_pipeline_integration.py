"""
Integration Test: Full Preprocessing Pipeline (Steps 1-6)

Runs a realistic scraped interview document through all 6 preprocessing
steps in sequence, validating that each step's output is valid input
for the next step and that the final output is a valid
ProcessedInterviewDocument.

All steps are instantiated directly (no GCS, no Airflow).
NER is disabled so spaCy models are not required in CI.
"""
import pytest

from src.preprocessing.steps.content_normalizer import ContentNormalizer
from src.preprocessing.steps.pii_remover import PIIRemover
from src.preprocessing.steps.quality_filter import QualityFilter
from src.preprocessing.steps.deduplicator import Deduplicator
from src.preprocessing.steps.entity_extractor import EntityExtractor
from src.preprocessing.steps.schema_validator import SchemaValidator
from src.preprocessing.steps.base import StepResult
from src.data_models.preprocessed_document import ProcessedInterviewDocument


# ── Fixtures ──

@pytest.fixture
def pipeline_steps():
    """Instantiate all 6 steps in pipeline order. NER disabled for CI."""
    return [
        ContentNormalizer(),
        PIIRemover(),
        QualityFilter(),
        Deduplicator(),
        EntityExtractor(ner_enabled=False),
        SchemaValidator(),
    ]


@pytest.fixture
def realistic_doc():
    """
    Realistic scraped interview document (Google SDE2, 5 rounds).
    Contains PII, markdown, multiple topics, and a clear outcome.
    """
    return {
        "document_id": "leetcode_integration_test_001",
        "source_platform": "leetcode",
        "source_url": "https://leetcode.com/discuss/post/99999/google-sde2-interview",
        "title": "Google SDE2 Interview Experience 2026",
        "raw_content": (
            "<p>I recently interviewed at <b>Google</b> for the SDE2 role.</p>\n"
            "<script>tracking()</script>\n"
            "There were **5 rounds** total.\n\n"
            "**Round 1** was a phone screen with DSA questions about "
            "dynamic programming and graphs. The interviewer asked me to "
            "solve a medium difficulty problem involving shortest paths.\n\n"
            "**Round 2** was a system design round where I had to design "
            "a URL shortener service. We discussed database sharding, "
            "caching strategies, and load balancing.\n\n"
            "**Round 3** was a behavioral round. Questions about leadership, "
            "conflict resolution, and past project experiences.\n\n"
            "**Round 4** was an onsite coding round focused on trees and "
            "binary search. I was asked to implement an LRU cache.\n\n"
            "**Round 5** was another onsite round with a system design "
            "problem about designing a notification system.\n\n"
            "Overall the process was medium difficulty. The interviewers "
            "were very friendly and professional throughout.\n\n"
            "I received the offer after 2 weeks! Feel free to reach out "
            "at candidate@example.com or call me at +1-555-123-4567.\n\n"
            "Hope this helps! 🚀🎉"
        ),
        "published_at": "2026-02-01T10:00:00Z",
        "scraped_at": "2026-02-02T08:00:00Z",
        "scrape_type": "bulk",
        "scrape_batch_id": "2026-02-02_bulk",
        "source_metadata": {"tags": ["Interview"], "company": "Google"},
        "content_hash": "abcdef1234567890" * 4,
    }


@pytest.fixture
def invalid_doc():
    """
    Minimal doc with no extractable company/role and very short content.
    Should be filtered at some point during the pipeline.
    """
    return {
        "document_id": "leetcode_integration_invalid_001",
        "source_platform": "leetcode",
        "source_url": "https://leetcode.com/discuss/post/00000/empty",
        "title": "Quick question",
        "raw_content": "How do I prepare?",
        "published_at": None,
        "scraped_at": "2026-02-02T08:00:00Z",
        "scrape_type": "bulk",
        "scrape_batch_id": "2026-02-02_bulk",
        "source_metadata": {},
        "content_hash": "0" * 64,
    }


def _run_pipeline(steps, doc):
    """
    Run a single document through all steps using run_batch().
    Returns (final_output_or_none, list_of_step_results).
    """
    docs = [doc]
    step_results = []

    for step in steps:
        docs, result = step.run_batch(docs)
        step_results.append(result)
        if not docs:
            return None, step_results

    return docs[0] if docs else None, step_results


# ── Full pipeline success ──

class TestFullPipelineSuccess:
    def test_realistic_doc_produces_processed_document(self, pipeline_steps, realistic_doc):
        """A realistic interview doc passes all 6 steps and produces a valid output."""
        result, _ = _run_pipeline(pipeline_steps, realistic_doc)
        assert result is not None
        assert isinstance(result, ProcessedInterviewDocument)

    def test_no_step_crashes(self, pipeline_steps, realistic_doc):
        """Every step completes without raising an exception."""
        _, step_results = _run_pipeline(pipeline_steps, realistic_doc)
        for sr in step_results:
            assert sr.error_count == 0, f"Step '{sr.step_name}' had {sr.error_count} errors"

    def test_all_six_steps_ran(self, pipeline_steps, realistic_doc):
        """All 6 steps execute and produce StepResult objects."""
        _, step_results = _run_pipeline(pipeline_steps, realistic_doc)
        assert len(step_results) == 6
        expected_names = [
            "content_normalizer", "pii_remover", "quality_filter",
            "deduplicator", "entity_extractor", "schema_validator",
        ]
        actual_names = [sr.step_name for sr in step_results]
        assert actual_names == expected_names


# ── Pipeline preserves required fields ──

class TestPipelinePreservesFields:
    def test_document_id_preserved(self, pipeline_steps, realistic_doc):
        result, _ = _run_pipeline(pipeline_steps, realistic_doc)
        assert result.document_id == "leetcode_integration_test_001"

    def test_company_extracted(self, pipeline_steps, realistic_doc):
        result, _ = _run_pipeline(pipeline_steps, realistic_doc)
        assert result.company is not None
        assert result.company.strip() != ""

    def test_role_extracted(self, pipeline_steps, realistic_doc):
        result, _ = _run_pipeline(pipeline_steps, realistic_doc)
        assert result.role is not None
        assert result.role.strip() != ""

    def test_content_not_empty(self, pipeline_steps, realistic_doc):
        result, _ = _run_pipeline(pipeline_steps, realistic_doc)
        assert result.content is not None
        assert len(result.content) > 0

    def test_content_hash_present(self, pipeline_steps, realistic_doc):
        result, _ = _run_pipeline(pipeline_steps, realistic_doc)
        assert result.content_hash is not None
        assert len(result.content_hash) > 0

    def test_word_count_positive(self, pipeline_steps, realistic_doc):
        result, _ = _run_pipeline(pipeline_steps, realistic_doc)
        assert result.word_count > 0

    def test_platform_valid(self, pipeline_steps, realistic_doc):
        result, _ = _run_pipeline(pipeline_steps, realistic_doc)
        assert result.source_platform == "leetcode"


# ── Content transformations applied ──

class TestContentTransformations:
    def test_html_stripped(self, pipeline_steps, realistic_doc):
        result, _ = _run_pipeline(pipeline_steps, realistic_doc)
        assert "<script>" not in result.content
        assert "<b>" not in result.content
        assert "<p>" not in result.content

    def test_pii_redacted(self, pipeline_steps, realistic_doc):
        result, _ = _run_pipeline(pipeline_steps, realistic_doc)
        assert "candidate@example.com" not in result.content
        assert "+1-555-123-4567" not in result.content

    def test_emojis_removed(self, pipeline_steps, realistic_doc):
        result, _ = _run_pipeline(pipeline_steps, realistic_doc)
        assert "🚀" not in result.content
        assert "🎉" not in result.content


# ── Step result tracking ──

class TestStepResultTracking:
    def test_each_step_returns_step_result(self, pipeline_steps, realistic_doc):
        _, step_results = _run_pipeline(pipeline_steps, realistic_doc)
        for sr in step_results:
            assert isinstance(sr, StepResult)

    def test_input_equals_output_plus_filtered(self, pipeline_steps, realistic_doc):
        _, step_results = _run_pipeline(pipeline_steps, realistic_doc)
        for sr in step_results:
            assert sr.input_count == sr.output_count + sr.filtered_count + sr.error_count, (
                f"Step '{sr.step_name}': input={sr.input_count} != "
                f"output={sr.output_count} + filtered={sr.filtered_count} + errors={sr.error_count}"
            )

    def test_first_step_input_count_is_one(self, pipeline_steps, realistic_doc):
        _, step_results = _run_pipeline(pipeline_steps, realistic_doc)
        assert step_results[0].input_count == 1

    def test_duration_nonnegative(self, pipeline_steps, realistic_doc):
        _, step_results = _run_pipeline(pipeline_steps, realistic_doc)
        for sr in step_results:
            assert sr.duration_seconds >= 0.0


# ── Invalid doc gets filtered ──

class TestInvalidDocFiltered:
    def test_invalid_doc_does_not_produce_output(self, pipeline_steps, invalid_doc):
        """A doc with no company/role and short content gets filtered."""
        result, _ = _run_pipeline(pipeline_steps, invalid_doc)
        assert result is None

    def test_invalid_doc_filtered_at_some_step(self, pipeline_steps, invalid_doc):
        """At least one step filters the invalid doc (filtered_count > 0)."""
        _, step_results = _run_pipeline(pipeline_steps, invalid_doc)
        total_filtered = sum(sr.filtered_count for sr in step_results)
        assert total_filtered > 0

    def test_pipeline_does_not_crash_on_invalid_doc(self, pipeline_steps, invalid_doc):
        """Pipeline completes without exceptions even for invalid input."""
        _, step_results = _run_pipeline(pipeline_steps, invalid_doc)
        for sr in step_results:
            assert sr.error_count == 0


# ── GFG platform doc ──

class TestGFGPlatformDoc:
    @pytest.fixture
    def gfg_doc(self):
        return {
            "document_id": "gfg_integration_test_001",
            "source_platform": "gfg",
            "source_url": "https://www.geeksforgeeks.org/amazon-sde1-interview/",
            "title": "Amazon SDE1 Interview Experience",
            "raw_content": (
                "I applied for SDE1 at Amazon through a referral. "
                "The process had 4 rounds. Round 1 was an online assessment "
                "with two coding problems on arrays and dynamic programming. "
                "Round 2 was a technical phone screen about trees and graphs. "
                "Round 3 was a system design round where I designed a parking lot system. "
                "Round 4 was a bar raiser behavioral round about leadership principles. "
                "Topics covered included arrays, trees, dynamic programming, "
                "and Amazon leadership principles. "
                "I received an offer after 3 weeks. The difficulty was medium to hard. "
                "Contact me at candidate@gmail.com for more details."
            ),
            "published_at": "2026-01-10T10:00:00Z",
            "scraped_at": "2026-01-11T08:00:00Z",
            "scrape_type": "bulk",
            "scrape_batch_id": "2026-01-11_bulk",
            "source_metadata": {"tags": ["Interview Experiences"]},
            "content_hash": "cafebabe" * 8,
        }

    def test_gfg_doc_produces_valid_output(self, pipeline_steps, gfg_doc):
        result, _ = _run_pipeline(pipeline_steps, gfg_doc)
        assert result is not None
        assert isinstance(result, ProcessedInterviewDocument)

    def test_gfg_platform_normalized(self, pipeline_steps, gfg_doc):
        result, _ = _run_pipeline(pipeline_steps, gfg_doc)
        assert result.source_platform == "gfg"