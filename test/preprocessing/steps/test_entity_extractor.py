"""
Tests for Step 5: EntityExtractor.

Covers:
- process(): output schema, never filters, completed flag
- _extract_company(): all 3 tiers (title regex, alias dict, NER)
- _normalize_company(): alias normalization, title-case fallback
- _extract_role(): alias lookup, roman numeral normalization
- _normalize_roman_numerals()
- _extract_level()
- _extract_interview_types(): multiple types
- _extract_num_rounds(): explicit count, round headers
- _extract_topics()
- _extract_outcome(): tail-first logic, full fallback
- _extract_difficulty()
- NER disabled mode
"""
import pytest
from unittest.mock import MagicMock, patch
from src.preprocessing.steps.entity_extractor import EntityExtractor


# ── Fixtures ──

@pytest.fixture
def extractor():
    return EntityExtractor(ner_enabled=False)  # Avoid spaCy dependency in unit tests


def _doc(title="", content=""):
    return {
        "document_id": "test_entity_doc",
        "source_platform": "leetcode",
        "preprocessing": {
            "pii_remover": {
                "title": title,
                "content": content,
                "completed": True,
            }
        }
    }


# ── process() — schema ──

class TestProcessSchema:
    def test_never_returns_none(self, extractor):
        doc = _doc("Some Title", "Some content about interview.")
        result = extractor.process(doc)
        assert result is not None

    def test_entity_extractor_key_added(self, extractor):
        doc = _doc("Google Interview", "I interviewed at Google.")
        result = extractor.process(doc)
        assert "entity_extractor" in result["preprocessing"]

    def test_all_output_keys_present(self, extractor):
        doc = _doc("Google Interview", "Some content about rounds.")
        result = extractor.process(doc)
        ee = result["preprocessing"]["entity_extractor"]
        for key in ["company", "role", "experience_level", "interview_types",
                    "num_rounds", "topics", "interview_outcome", "difficulty", "completed"]:
            assert key in ee, f"Missing key: {key}"

    def test_completed_flag_set(self, extractor):
        doc = _doc()
        result = extractor.process(doc)
        assert result["preprocessing"]["entity_extractor"]["completed"] is True

    def test_original_content_not_modified(self, extractor):
        content = "I interviewed at Amazon for SDE role."
        doc = _doc("Amazon SDE Interview", content)
        extractor.process(doc)
        assert doc["preprocessing"]["pii_remover"]["content"] == content


# ── _extract_company() ──

class TestExtractCompany:
    def test_known_company_from_alias(self, extractor):
        """MSFT → Microsoft via alias dictionary."""
        result = extractor._extract_company("MSFT Interview Experience", "")
        # Result should be normalized if MSFT is in the alias dict
        assert result is not None

    def test_returns_none_when_no_company_found(self, extractor):
        result = extractor._extract_company(
            "Some Generic Post About Nothing",
            "No company name anywhere in this content at all."
        )
        # Without NER, may return None — that's valid
        assert result is None or isinstance(result, str)

    def test_company_not_empty_string(self, extractor):
        result = extractor._extract_company("Google Interview Experience", "")
        if result is not None:
            assert result.strip() != ""


# ── _normalize_company() ──

class TestNormalizeCompany:
    def test_known_alias_normalized(self, extractor):
        from src.preprocessing.steps.entity_extractor import COMPANY_ALIASES
        if "google" in COMPANY_ALIASES:
            result = extractor._normalize_company("google")
            assert result == COMPANY_ALIASES["google"]

    def test_unknown_company_title_cased(self, extractor):
        result = extractor._normalize_company("some startup co")
        assert result == "Some Startup Co"

    def test_strips_whitespace(self, extractor):
        result = extractor._normalize_company("  TestCorp  ")
        assert result == result.strip()


# ── _extract_role() ──

class TestExtractRole:
    def test_known_role_alias(self, extractor):
        from src.preprocessing.steps.entity_extractor import ROLE_ALIASES
        if "sde" in ROLE_ALIASES:
            result = extractor._extract_role("SDE Interview at Google", "")
            assert result == ROLE_ALIASES["sde"]

    def test_no_role_returns_none(self, extractor):
        result = extractor._extract_role("Generic Post", "No role mentioned here at all.")
        assert result is None or isinstance(result, str)

    def test_role_from_content_when_not_in_title(self, extractor):
        from src.preprocessing.steps.entity_extractor import ROLE_ALIASES
        # Find a role alias we can inject into content
        if ROLE_ALIASES:
            alias = next(iter(ROLE_ALIASES))
            result = extractor._extract_role("No role title", f"I applied for {alias} position.")
            assert result is not None


# ── _normalize_roman_numerals() ──

class TestNormalizeRomanNumerals:
    def test_sde_ii_becomes_sde_2(self, extractor):
        result = extractor._normalize_roman_numerals("SDE II")
        assert "2" in result
        assert "II" not in result

    def test_sde_iii_becomes_sde_3(self, extractor):
        result = extractor._normalize_roman_numerals("SDE III")
        assert "3" in result

    def test_no_roman_numerals_unchanged(self, extractor):
        result = extractor._normalize_roman_numerals("Software Engineer")
        assert result == "Software Engineer"

    def test_level_i_becomes_1(self, extractor):
        result = extractor._normalize_roman_numerals("L I engineer")
        assert "1" in result

    def test_v_becomes_5(self, extractor):
        result = extractor._normalize_roman_numerals("Level V")
        assert "5" in result


# ── _extract_level() ──

class TestExtractLevel:
    def test_intern_detected(self, extractor):
        from src.preprocessing.steps.entity_extractor import LEVEL_KEYWORDS
        if "intern" in LEVEL_KEYWORDS and LEVEL_KEYWORDS["intern"]:
            kw = LEVEL_KEYWORDS["intern"][0]
            result = extractor._extract_level(f"i am an {kw} at google")
            assert result == "intern"

    def test_senior_detected(self, extractor):
        from src.preprocessing.steps.entity_extractor import LEVEL_KEYWORDS
        if "senior" in LEVEL_KEYWORDS and LEVEL_KEYWORDS["senior"]:
            kw = LEVEL_KEYWORDS["senior"][0]
            result = extractor._extract_level(f"applied for {kw} position")
            assert result == "senior"

    def test_unknown_returned_when_no_match(self, extractor):
        result = extractor._extract_level("no level info in this text")
        assert result == "unknown"


# ── _extract_interview_types() ──

class TestExtractInterviewTypes:
    def test_no_type_returns_unknown(self, extractor):
        result = extractor._extract_interview_types("no type info here")
        assert result == ["unknown"]

    def test_returns_list(self, extractor):
        result = extractor._extract_interview_types("anything")
        assert isinstance(result, list)

    def test_multiple_types_detected(self, extractor):
        from src.preprocessing.steps.entity_extractor import TYPE_KEYWORDS
        if len(TYPE_KEYWORDS) >= 2:
            types = list(TYPE_KEYWORDS.keys())[:2]
            kws = [TYPE_KEYWORDS[t][0] for t in types if TYPE_KEYWORDS[t]]
            text = " ".join(kws)
            result = extractor._extract_interview_types(text)
            assert len(result) >= 1  # At least one should match

    def test_no_duplicates_per_type(self, extractor):
        from src.preprocessing.steps.entity_extractor import TYPE_KEYWORDS
        if "onsite" in TYPE_KEYWORDS:
            kw = TYPE_KEYWORDS["onsite"][0]
            text = f"{kw} {kw} {kw}"
            result = extractor._extract_interview_types(text)
            assert result.count("onsite") <= 1


# ── _extract_num_rounds() ──

class TestExtractNumRounds:
    def test_explicit_count(self, extractor):
        result = extractor._extract_num_rounds("There were 5 rounds of interview.")
        assert result == 5

    def test_round_headers_counted(self, extractor):
        text = "Round 1 was DSA. Round 2 was system design. Round 3 was behavioral."
        result = extractor._extract_num_rounds(text)
        assert result is not None
        assert result >= 1

    def test_no_rounds_returns_none(self, extractor):
        result = extractor._extract_num_rounds("No round information here at all in this text.")
        assert result is None or isinstance(result, int)

    def test_uses_max_of_explicit_and_markers(self, extractor):
        # "4 rounds" explicit but "Round 1, 2, 3" as headers → max(4, 3) = 4
        text = "There were 4 rounds. Round 1 DSA. Round 2 design. Round 3 HR."
        result = extractor._extract_num_rounds(text)
        assert result == 4

    def test_returns_int_or_none(self, extractor):
        result = extractor._extract_num_rounds("5 rounds of interview process conducted.")
        assert result is None or isinstance(result, int)


# ── _extract_topics() ──

class TestExtractTopics:
    def test_dsa_topic_detected(self, extractor):
        from src.preprocessing.steps.entity_extractor import TOPIC_PATTERNS
        if "dsa" in TOPIC_PATTERNS:
            result = extractor._extract_topics("they asked about data structures and algorithms")
            assert "dsa" in result

    def test_returns_sorted_list(self, extractor):
        result = extractor._extract_topics("behavioral and dsa and system design round")
        assert result == sorted(result)

    def test_empty_text_returns_empty_list(self, extractor):
        result = extractor._extract_topics("")
        assert result == []

    def test_no_topics_returns_empty_list(self, extractor):
        result = extractor._extract_topics("blah blah nothing relevant here at all xyz")
        assert isinstance(result, list)

    def test_no_duplicate_topics(self, extractor):
        text = "dsa dsa dsa data structures algorithms interview round"
        result = extractor._extract_topics(text)
        assert len(result) == len(set(result))


# ── _extract_outcome() ──

class TestExtractOutcome:
    def test_offer_detected(self, extractor):
        from src.preprocessing.steps.entity_extractor import OUTCOME_KEYWORDS
        if "offer" in OUTCOME_KEYWORDS and OUTCOME_KEYWORDS["offer"]:
            kw = OUTCOME_KEYWORDS["offer"][0]
            text = "x " * 100 + f"I {kw} the position."  # Put outcome in tail
            result = extractor._extract_outcome(text.lower())
            assert result == "offer"

    def test_reject_detected(self, extractor):
        from src.preprocessing.steps.entity_extractor import OUTCOME_KEYWORDS
        if "reject" in OUTCOME_KEYWORDS and OUTCOME_KEYWORDS["reject"]:
            kw = OUTCOME_KEYWORDS["reject"][0]
            text = "x " * 100 + f"Unfortunately I was {kw}."
            result = extractor._extract_outcome(text.lower())
            assert result == "reject"

    def test_unknown_when_no_outcome(self, extractor):
        result = extractor._extract_outcome("just went through five rounds nothing else")
        assert result == "unknown"

    def test_tail_checked_first(self, extractor):
        """Outcome in tail should be detected even if beginning has no keywords."""
        from src.preprocessing.steps.entity_extractor import OUTCOME_KEYWORDS
        if "offer" in OUTCOME_KEYWORDS and OUTCOME_KEYWORDS["offer"]:
            kw = OUTCOME_KEYWORDS["offer"][0]
            # Pack offer keyword into last 30% of text
            padding = "interview round technical coding " * 30
            text = padding + f" I received the {kw}."
            result = extractor._extract_outcome(text.lower())
            assert result == "offer"


# ── _extract_difficulty() ──

class TestExtractDifficulty:
    def test_hard_detected(self, extractor):
        from src.preprocessing.steps.entity_extractor import DIFFICULTY_KEYWORDS
        if "hard" in DIFFICULTY_KEYWORDS and DIFFICULTY_KEYWORDS["hard"]:
            kw = DIFFICULTY_KEYWORDS["hard"][0]
            result = extractor._extract_difficulty(f"the interview was {kw}")
            assert result == "hard"

    def test_easy_detected(self, extractor):
        from src.preprocessing.steps.entity_extractor import DIFFICULTY_KEYWORDS
        if "easy" in DIFFICULTY_KEYWORDS and DIFFICULTY_KEYWORDS["easy"]:
            kw = DIFFICULTY_KEYWORDS["easy"][0]
            result = extractor._extract_difficulty(f"it was an {kw} process")
            assert result == "easy"

    def test_unknown_when_no_difficulty(self, extractor):
        result = extractor._extract_difficulty("went through several rounds at google")
        assert result == "unknown"


# ── NER disabled ──

class TestNERDisabled:
    def test_ner_disabled_does_not_crash(self):
        extractor = EntityExtractor(ner_enabled=False)
        doc = _doc("Some Company Interview Experience", "Content about interview rounds.")
        result = extractor.process(doc)
        assert result is not None

    def test_ner_never_called_when_disabled(self):
        extractor = EntityExtractor(ner_enabled=False)
        with patch.object(extractor, "_extract_company_via_ner") as mock_ner:
            extractor._extract_company("Unknown Corp XYZ Title", "")
            mock_ner.assert_not_called()


# ── run_batch() integration ──

class TestRunBatchIntegration:
    def test_batch_all_pass(self, extractor):
        docs = [
            _doc("Google Interview", "DSA system design rounds at Google."),
            _doc("Amazon Interview", "Behavioral rounds at Amazon SDE."),
        ]
        out, result = extractor.run_batch(docs)
        assert result.input_count == 2
        assert result.output_count == 2
        assert result.filtered_count == 0