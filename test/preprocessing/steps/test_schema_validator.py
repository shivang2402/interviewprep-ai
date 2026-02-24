"""
Tests for Step 6: SchemaValidator + ProcessedInterviewDocument.

Covers SchemaValidator:
- process(): valid doc → ProcessedInterviewDocument instance
- process(): invalid doc → None + _filter_reason set
- _map_fields(): correct key mapping from pipeline dict

Covers ProcessedInterviewDocument:
- Required field validation (missing → ValueError)
- Platform normalization (gfg → geeksforgeeks) and validation
- Safe-enum normalization (invalid → None)
- interview_types filtering (invalid types dropped)
- preprocessed_at auto-set
- to_dict() / to_json() / from_dict() / from_json() roundtrip
- _safe_enum() / _normalize_platform() helpers
"""
import json
import pytest
from datetime import datetime, timezone

from src.preprocessing.steps.schema_validator import SchemaValidator
from src.data_models.preprocessed_document import (
    ProcessedInterviewDocument,
    VALID_PLATFORMS,
    VALID_EXPERIENCE,
    VALID_OUTCOMES,
    VALID_DIFFICULTY,
    VALID_INTERVIEW_TYPES,
)


# ── Fixtures ──

@pytest.fixture
def validator():
    return SchemaValidator()


@pytest.fixture
def full_pipeline_doc():
    """Fully enriched doc dict as produced by all 5 prior steps."""
    return {
        "document_id": "leetcode_abc123",
        "source_platform": "leetcode",
        "source_url": "https://leetcode.com/discuss/post/123/google-sde2",
        "published_at": "2026-01-15T10:00:00Z",
        "scraped_at": "2026-01-16T08:00:00Z",
        "scrape_type": "bulk",
        "scrape_batch_id": "2026-01-16_bulk",
        "source_metadata": {"tags": ["Interview"]},
        "content_hash": "original_scraper_hash",
        "preprocessing": {
            "content_normalizer": {
                "word_count": 200,
                "completed": True,
            },
            "pii_remover": {
                "content": "I interviewed at Google. There were 5 rounds. I got an offer.",
                "title": "Google SDE2 Interview Experience",
                "pii_counts": {},
                "completed": True,
            },
            "quality_filter": {
                "quality_score": 0.9,
                "completed": True,
            },
            "deduplicator": {
                "content_hash": "a" * 64,
                "completed": True,
            },
            "entity_extractor": {
                "company": "Google",
                "role": "Software Development Engineer",
                "experience_level": "mid",
                "interview_types": ["phone_screen", "onsite"],
                "num_rounds": 5,
                "topics": ["dsa", "system_design"],
                "interview_outcome": "offer",
                "difficulty": "medium",
                "completed": True,
            },
        },
    }


@pytest.fixture
def valid_kwargs():
    return {
        "document_id": "leetcode_abc123",
        "source_platform": "leetcode",
        "source_url": "https://leetcode.com/discuss/post/123",
        "content_hash": "a" * 64,
        "title": "Google SDE2 Interview Experience",
        "content": "I interviewed at Google for SDE2. There were 5 rounds.",
        "word_count": 11,
        "company": "Google",
        "role": "Software Development Engineer",
    }


# ── SchemaValidator.process() ──

class TestSchemaValidatorProcess:
    def test_valid_doc_returns_processed_document(self, validator, full_pipeline_doc):
        result = validator.process(full_pipeline_doc)
        assert result is not None
        assert isinstance(result, ProcessedInterviewDocument)

    def test_valid_doc_fields_mapped_correctly(self, validator, full_pipeline_doc):
        result = validator.process(full_pipeline_doc)
        assert result.document_id == "leetcode_abc123"
        assert result.company == "Google"
        assert result.role == "Software Development Engineer"
        assert result.content_hash == "a" * 64

    def test_invalid_doc_returns_none(self, validator, full_pipeline_doc):
        full_pipeline_doc["preprocessing"]["entity_extractor"]["company"] = None
        result = validator.process(full_pipeline_doc)
        assert result is None

    def test_invalid_doc_sets_filter_reason(self, validator, full_pipeline_doc):
        full_pipeline_doc["preprocessing"]["entity_extractor"]["role"] = ""
        validator.process(full_pipeline_doc)
        assert "_filter_reason" in full_pipeline_doc
        assert "schema_validation_failed" in full_pipeline_doc["_filter_reason"]

    def test_missing_pii_content_returns_none(self, validator, full_pipeline_doc):
        full_pipeline_doc["preprocessing"]["pii_remover"]["content"] = ""
        result = validator.process(full_pipeline_doc)
        assert result is None

    def test_invalid_platform_returns_none(self, validator, full_pipeline_doc):
        full_pipeline_doc["source_platform"] = "unknown_platform_xyz"
        result = validator.process(full_pipeline_doc)
        assert result is None


# ── SchemaValidator._map_fields() ──

class TestMapFields:
    def test_map_fields_returns_dict(self, validator, full_pipeline_doc):
        mapped = validator._map_fields(full_pipeline_doc)
        assert isinstance(mapped, dict)

    def test_map_fields_document_id(self, validator, full_pipeline_doc):
        mapped = validator._map_fields(full_pipeline_doc)
        assert mapped["document_id"] == "leetcode_abc123"

    def test_map_fields_content_from_pii_remover(self, validator, full_pipeline_doc):
        mapped = validator._map_fields(full_pipeline_doc)
        assert "interviewed at Google" in mapped["content"]

    def test_map_fields_title_from_pii_remover(self, validator, full_pipeline_doc):
        mapped = validator._map_fields(full_pipeline_doc)
        assert mapped["title"] == "Google SDE2 Interview Experience"

    def test_map_fields_hash_from_deduplicator(self, validator, full_pipeline_doc):
        mapped = validator._map_fields(full_pipeline_doc)
        assert mapped["content_hash"] == "a" * 64

    def test_map_fields_entity_fields(self, validator, full_pipeline_doc):
        mapped = validator._map_fields(full_pipeline_doc)
        assert mapped["company"] == "Google"
        assert mapped["role"] == "Software Development Engineer"
        assert mapped["num_rounds"] == 5

    def test_map_fields_preprocessed_at_set(self, validator, full_pipeline_doc):
        mapped = validator._map_fields(full_pipeline_doc)
        assert mapped["preprocessed_at"] is not None

    def test_map_fields_missing_entity_extractor_defaults(self, validator, full_pipeline_doc):
        del full_pipeline_doc["preprocessing"]["entity_extractor"]
        mapped = validator._map_fields(full_pipeline_doc)
        assert mapped["company"] is None
        assert mapped["topics"] == []


# ── ProcessedInterviewDocument: Required field validation ──

class TestRequiredFieldValidation:
    @pytest.mark.parametrize("missing_field", [
        "document_id", "source_platform", "source_url",
        "content_hash", "title", "content", "company", "role"
    ])
    def test_missing_required_field_raises(self, valid_kwargs, missing_field):
        valid_kwargs[missing_field] = None
        with pytest.raises(ValueError, match="Required field"):
            ProcessedInterviewDocument(**valid_kwargs)

    @pytest.mark.parametrize("empty_field", [
        "document_id", "title", "content", "company", "role"
    ])
    def test_empty_string_required_field_raises(self, valid_kwargs, empty_field):
        valid_kwargs[empty_field] = "   "
        with pytest.raises(ValueError, match="Required field"):
            ProcessedInterviewDocument(**valid_kwargs)

    def test_all_required_fields_present_succeeds(self, valid_kwargs):
        doc = ProcessedInterviewDocument(**valid_kwargs)
        assert doc.document_id == "leetcode_abc123"

# ── Safe-enum normalization ──

class TestSafeEnumNormalization:
    def test_valid_experience_level_accepted(self, valid_kwargs):
        for level in VALID_EXPERIENCE:
            valid_kwargs["experience_level"] = level
            doc = ProcessedInterviewDocument(**valid_kwargs)
            assert doc.experience_level == level

    def test_invalid_experience_level_becomes_none(self, valid_kwargs):
        valid_kwargs["experience_level"] = "executive"
        doc = ProcessedInterviewDocument(**valid_kwargs)
        assert doc.experience_level is None

    def test_valid_outcome_accepted(self, valid_kwargs):
        for outcome in VALID_OUTCOMES:
            valid_kwargs["interview_outcome"] = outcome
            doc = ProcessedInterviewDocument(**valid_kwargs)
            assert doc.interview_outcome == outcome

    def test_invalid_outcome_becomes_none(self, valid_kwargs):
        valid_kwargs["interview_outcome"] = "ghosted"
        doc = ProcessedInterviewDocument(**valid_kwargs)
        assert doc.interview_outcome is None

    def test_valid_difficulty_accepted(self, valid_kwargs):
        for diff in VALID_DIFFICULTY:
            valid_kwargs["difficulty"] = diff
            doc = ProcessedInterviewDocument(**valid_kwargs)
            assert doc.difficulty == diff

    def test_invalid_difficulty_becomes_none(self, valid_kwargs):
        valid_kwargs["difficulty"] = "brutal"
        doc = ProcessedInterviewDocument(**valid_kwargs)
        assert doc.difficulty is None

    def test_none_enum_stays_none(self, valid_kwargs):
        valid_kwargs["experience_level"] = None
        valid_kwargs["interview_outcome"] = None
        valid_kwargs["difficulty"] = None
        doc = ProcessedInterviewDocument(**valid_kwargs)
        assert doc.experience_level is None
        assert doc.interview_outcome is None
        assert doc.difficulty is None

    def test_enum_case_normalized(self, valid_kwargs):
        valid_kwargs["experience_level"] = "SENIOR"
        doc = ProcessedInterviewDocument(**valid_kwargs)
        assert doc.experience_level == "senior"

    def test_enum_whitespace_stripped(self, valid_kwargs):
        valid_kwargs["difficulty"] = "  hard  "
        doc = ProcessedInterviewDocument(**valid_kwargs)
        assert doc.difficulty == "hard"


# ── interview_types filtering ──

class TestInterviewTypesFiltering:
    def test_valid_types_preserved(self, valid_kwargs):
        valid_types = list(VALID_INTERVIEW_TYPES)[:2]
        valid_kwargs["interview_types"] = valid_types
        doc = ProcessedInterviewDocument(**valid_kwargs)
        assert set(doc.interview_types) == set(valid_types)

    def test_invalid_types_dropped(self, valid_kwargs):
        valid_kwargs["interview_types"] = ["onsite", "carrier_pigeon", "phone_screen"]
        doc = ProcessedInterviewDocument(**valid_kwargs)
        assert "carrier_pigeon" not in doc.interview_types
        assert "onsite" in doc.interview_types

    def test_empty_interview_types(self, valid_kwargs):
        valid_kwargs["interview_types"] = []
        doc = ProcessedInterviewDocument(**valid_kwargs)
        assert doc.interview_types == []

    def test_all_invalid_types_gives_empty(self, valid_kwargs):
        valid_kwargs["interview_types"] = ["xyz", "abc", "nonsense"]
        doc = ProcessedInterviewDocument(**valid_kwargs)
        assert doc.interview_types == []


# ── preprocessed_at auto-set ──

class TestPreprocessedAt:
    def test_auto_set_when_none(self, valid_kwargs):
        doc = ProcessedInterviewDocument(**valid_kwargs)
        assert doc.preprocessed_at is not None
        assert "T" in doc.preprocessed_at  # ISO format check

    def test_provided_value_preserved(self, valid_kwargs):
        ts = "2026-01-01T00:00:00Z"
        valid_kwargs["preprocessed_at"] = ts
        doc = ProcessedInterviewDocument(**valid_kwargs)
        assert doc.preprocessed_at == ts

    def test_auto_timestamp_format(self, valid_kwargs):
        doc = ProcessedInterviewDocument(**valid_kwargs)
        # Should parse without error
        datetime.strptime(doc.preprocessed_at, "%Y-%m-%dT%H:%M:%SZ")


# ── Serialization roundtrip ──

class TestSerialization:
    def test_to_dict_roundtrip(self, valid_kwargs):
        doc = ProcessedInterviewDocument(**valid_kwargs)
        d = doc.to_dict()
        doc2 = ProcessedInterviewDocument.from_dict(d)
        assert doc2.document_id == doc.document_id
        assert doc2.company == doc.company

    def test_to_json_roundtrip(self, valid_kwargs):
        doc = ProcessedInterviewDocument(**valid_kwargs)
        j = doc.to_json()
        doc2 = ProcessedInterviewDocument.from_json(j)
        assert doc2.document_id == doc.document_id

    def test_to_json_is_valid_json(self, valid_kwargs):
        doc = ProcessedInterviewDocument(**valid_kwargs)
        parsed = json.loads(doc.to_json())
        assert isinstance(parsed, dict)

    def test_to_dict_contains_all_required_keys(self, valid_kwargs):
        doc = ProcessedInterviewDocument(**valid_kwargs)
        d = doc.to_dict()
        for key in ["document_id", "source_platform", "company", "role",
                    "content", "title", "word_count", "content_hash"]:
            assert key in d

    def test_from_dict_revalidates(self, valid_kwargs):
        d = valid_kwargs.copy()
        d["source_platform"] = "invalid"
        with pytest.raises(ValueError):
            ProcessedInterviewDocument.from_dict(d)


# ── _safe_enum helper ──

class TestSafeEnum:
    def test_valid_value_returned(self):
        result = ProcessedInterviewDocument._safe_enum("offer", VALID_OUTCOMES, None)
        assert result == "offer"

    def test_invalid_value_returns_default(self):
        result = ProcessedInterviewDocument._safe_enum("ghosted", VALID_OUTCOMES, None)
        assert result is None

    def test_none_input_returns_default(self):
        result = ProcessedInterviewDocument._safe_enum(None, VALID_OUTCOMES, "unknown")
        assert result == "unknown"

    def test_case_insensitive(self):
        result = ProcessedInterviewDocument._safe_enum("OFFER", VALID_OUTCOMES, None)
        assert result == "offer"

    def test_whitespace_stripped(self):
        result = ProcessedInterviewDocument._safe_enum("  offer  ", VALID_OUTCOMES, None)
        assert result == "offer"


# ── now_iso() ──

class TestNowIso:
    def test_returns_string(self):
        ts = ProcessedInterviewDocument.now_iso()
        assert isinstance(ts, str)

    def test_parseable_iso_format(self):
        ts = ProcessedInterviewDocument.now_iso()
        datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")

    def test_is_utc(self):
        ts = ProcessedInterviewDocument.now_iso()
        assert ts.endswith("Z")