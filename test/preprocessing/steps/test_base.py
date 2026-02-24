"""
Tests for base.py — StepResult dataclass and PreprocessingStep.run_batch.
Tests use a concrete minimal subclass since the base is abstract.
"""
import pytest
from src.preprocessing.steps.base import PreprocessingStep, StepResult


# ── Concrete stubs ──

class PassThroughStep(PreprocessingStep):
    """Returns doc unchanged."""
    @property
    def name(self): return "pass_through"
    def process(self, doc): return doc


class FilterAllStep(PreprocessingStep):
    """Filters every doc (returns None)."""
    @property
    def name(self): return "filter_all"
    def process(self, doc):
        doc["_filter_reason"] = "test_filter"
        return None


class FilterEvenStep(PreprocessingStep):
    """Filters docs whose index (stored in doc['i']) is even."""
    @property
    def name(self): return "filter_even"
    def process(self, doc):
        if doc["i"] % 2 == 0:
            doc["_filter_reason"] = "even_index"
            return None
        return doc


class ErrorStep(PreprocessingStep):
    """Raises an exception on every doc."""
    @property
    def name(self): return "error_step"
    def process(self, doc):
        raise ValueError("intentional test error")


class MutatingStep(PreprocessingStep):
    """Adds a 'processed' key to each doc."""
    @property
    def name(self): return "mutating_step"
    def process(self, doc):
        doc["processed"] = True
        return doc


# ── StepResult tests ──

class TestStepResult:
    def test_pass_rate_zero_input(self):
        r = StepResult(step_name="s")
        assert r.pass_rate == 0.0

    def test_pass_rate_all_pass(self):
        r = StepResult(step_name="s", input_count=10, output_count=10)
        assert r.pass_rate == 1.0

    def test_pass_rate_half(self):
        r = StepResult(step_name="s", input_count=10, output_count=5)
        assert r.pass_rate == 0.5

    def test_default_values(self):
        r = StepResult(step_name="my_step")
        assert r.input_count == 0
        assert r.output_count == 0
        assert r.filtered_count == 0
        assert r.error_count == 0
        assert r.duration_seconds == 0.0
        assert r.filter_reasons == {}

    def test_filter_reasons_mutable(self):
        r = StepResult(step_name="s")
        r.filter_reasons["reason_a"] = 3
        assert r.filter_reasons["reason_a"] == 3


# ── run_batch tests ──

class TestRunBatch:
    def _make_docs(self, n):
        return [{"document_id": f"doc_{i}", "i": i} for i in range(n)]

    def test_empty_batch(self):
        step = PassThroughStep()
        out, result = step.run_batch([])
        assert out == []
        assert result.input_count == 0
        assert result.output_count == 0

    def test_all_pass(self):
        step = PassThroughStep()
        docs = self._make_docs(5)
        out, result = step.run_batch(docs)
        assert len(out) == 5
        assert result.input_count == 5
        assert result.output_count == 5
        assert result.filtered_count == 0
        assert result.error_count == 0

    def test_all_filtered(self):
        step = FilterAllStep()
        docs = self._make_docs(4)
        out, result = step.run_batch(docs)
        assert out == []
        assert result.filtered_count == 4
        assert result.output_count == 0
        assert result.filter_reasons.get("test_filter") == 4

    def test_partial_filter(self):
        step = FilterEvenStep()
        docs = self._make_docs(6)  # indices 0..5; even → filtered
        out, result = step.run_batch(docs)
        assert len(out) == 3  # indices 1, 3, 5 survive
        assert result.output_count == 3
        assert result.filtered_count == 3

    def test_error_handling_does_not_stop_batch(self):
        step = ErrorStep()
        docs = self._make_docs(3)
        out, result = step.run_batch(docs)
        assert out == []
        assert result.error_count == 3
        assert result.filtered_count == 0

    def test_mutation_applied_to_output(self):
        step = MutatingStep()
        docs = [{"document_id": "d1"}]
        out, _ = step.run_batch(docs)
        assert out[0]["processed"] is True

    def test_duration_is_positive(self):
        step = PassThroughStep()
        _, result = step.run_batch(self._make_docs(2))
        assert result.duration_seconds >= 0.0

    def test_step_name_in_result(self):
        step = PassThroughStep()
        _, result = step.run_batch([])
        assert result.step_name == "pass_through"

    def test_filter_reason_unspecified_when_missing(self):
        """Docs filtered without _filter_reason default to 'unspecified'."""
        class SilentFilter(PreprocessingStep):
            @property
            def name(self): return "silent"
            def process(self, doc): return None  # no _filter_reason set

        step = SilentFilter()
        out, result = step.run_batch([{"document_id": "x"}])
        assert result.filter_reasons.get("unspecified") == 1

    def test_mixed_errors_and_filters(self):
        class MixedStep(PreprocessingStep):
            @property
            def name(self): return "mixed"
            def process(self, doc):
                if doc["i"] == 0: raise RuntimeError("boom")
                if doc["i"] == 1:
                    doc["_filter_reason"] = "filtered"
                    return None
                return doc

        step = MixedStep()
        docs = self._make_docs(4)
        out, result = step.run_batch(docs)
        assert result.error_count == 1
        assert result.filtered_count == 1
        assert result.output_count == 2

    def test_pass_rate_via_run_batch(self):
        step = FilterEvenStep()
        docs = self._make_docs(4)  # 0,1,2,3 → 1,3 survive
        _, result = step.run_batch(docs)
        assert result.pass_rate == pytest.approx(0.5)

    def test_abstract_enforcement(self):
        """Cannot instantiate PreprocessingStep directly."""
        with pytest.raises(TypeError):
            PreprocessingStep()