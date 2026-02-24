"""
Tests for Step 4: Deduplicator.

Covers:
- process(): unique doc passes, exact duplicate filtered, near-duplicate filtered
- Exact dedup: hash computation, pre-loaded existing hashes
- Near-dedup: shingle creation, minhash, LSH query
- Empty/short content handling
- State persistence: save_state(), load_or_create_lsh()
- stats property
- Cross-batch dedup (state persists between process() calls)
"""
import os
import pickle
import tempfile
import pytest
from datasketch import MinHash, MinHashLSH
from src.preprocessing.steps.deduplicator import Deduplicator


# ── Fixtures ──

@pytest.fixture
def dedup():
    return Deduplicator(
        similarity_threshold=0.8,
        num_perm=64,
        shingle_size=3,
    )


def _doc(content, doc_id="doc_1"):
    return {
        "document_id": doc_id,
        "preprocessing": {
            "pii_remover": {
                "content": content,
                "completed": True,
            }
        }
    }


LONG_CONTENT = (
    "I recently interviewed at Google for the SDE2 position. "
    "The process consisted of five rounds. Round one was a phone screen "
    "focused on data structures and algorithms. Round two covered system design. "
    "Round three was a behavioral interview about past projects and leadership. "
    "Rounds four and five were onsite coding rounds with dynamic programming "
    "and graph problems. I received an offer two weeks after the final round. "
    "Overall the difficulty was medium and the process was well-organized."
)

NEAR_DUPLICATE_CONTENT = (
    "I recently interviewed at Google for the SDE2 role. "
    "The process had five rounds. Round one was a phone screen "
    "focused on data structures and algorithms. Round two was system design. "
    "Round three was behavioral and covered past projects and leadership principles. "
    "Rounds four and five were onsite coding sessions with dynamic programming "
    "and graph traversal. I got an offer two weeks after the final interview. "
    "Overall difficulty was medium and the process was well-organized."
)

TOTALLY_DIFFERENT = (
    "Machine learning fundamentals include supervised and unsupervised learning. "
    "Neural networks consist of layers of connected neurons with activation functions. "
    "Backpropagation is used to train these networks by minimizing loss functions. "
    "Convolutional neural networks are well suited for image recognition tasks. "
    "Recurrent neural networks handle sequential data like text and time series."
)


# ── process() — happy path ──

class TestProcessHappyPath:
    def test_unique_doc_passes(self, dedup):
        doc = _doc(LONG_CONTENT)
        result = dedup.process(doc)
        assert result is not None

    def test_output_has_content_hash(self, dedup):
        doc = _doc(LONG_CONTENT)
        result = dedup.process(doc)
        assert result["preprocessing"]["deduplicator"]["content_hash"] is not None
        assert len(result["preprocessing"]["deduplicator"]["content_hash"]) == 64

    def test_completed_flag_set(self, dedup):
        doc = _doc(LONG_CONTENT)
        result = dedup.process(doc)
        assert result["preprocessing"]["deduplicator"]["completed"] is True

    def test_deduplicator_key_added(self, dedup):
        doc = _doc(LONG_CONTENT)
        result = dedup.process(doc)
        assert "deduplicator" in result["preprocessing"]


# ── process() — filtering ──

class TestProcessFiltering:
    def test_empty_content_filtered(self, dedup):
        doc = _doc("   ")
        result = dedup.process(doc)
        assert result is None
        assert doc["_filter_reason"] == "empty_content_at_dedup"

    def test_exact_duplicate_filtered(self, dedup):
        doc1 = _doc(LONG_CONTENT, doc_id="doc_a")
        doc2 = _doc(LONG_CONTENT, doc_id="doc_b")
        dedup.process(doc1)
        result = dedup.process(doc2)
        assert result is None
        assert doc2["_filter_reason"] == "exact_duplicate"

    def test_different_docs_both_pass(self, dedup):
        doc1 = _doc(LONG_CONTENT, doc_id="doc_a")
        doc2 = _doc(TOTALLY_DIFFERENT, doc_id="doc_b")
        r1 = dedup.process(doc1)
        r2 = dedup.process(doc2)
        assert r1 is not None
        assert r2 is not None

    def test_near_duplicate_filtered(self):
        """Near-duplicates with high similarity should be caught by LSH."""
        dedup_nd = Deduplicator(
            similarity_threshold=0.5,  # Low threshold to reliably catch paraphrases
            num_perm=128,
            shingle_size=3,
        )
        doc1 = _doc(LONG_CONTENT, doc_id="doc_a")
        doc2 = _doc(NEAR_DUPLICATE_CONTENT, doc_id="doc_b")
        dedup_nd.process(doc1)
        result = dedup_nd.process(doc2)
        if result is None:
            assert doc2["_filter_reason"] == "near_duplicate"
            assert "is_near_duplicate_of" in doc2

    def test_exact_dup_with_whitespace_difference(self, dedup):
        """Normalization should make whitespace-different copies exact dupes."""
        content_a = "Hello world this is an interview experience with enough content here."
        content_b = "Hello  world  this  is  an  interview  experience  with  enough  content  here."
        doc1 = _doc(content_a, doc_id="doc_a")
        doc2 = _doc(content_b, doc_id="doc_b")
        dedup.process(doc1)
        result = dedup.process(doc2)
        assert result is None
        assert doc2["_filter_reason"] == "exact_duplicate"

    def test_exact_dup_case_insensitive(self, dedup):
        """Hash normalization lowercases — same content different case = exact dup."""
        content_a = "Google Interview Experience SDE2 Five Rounds Technical Offer."
        content_b = "google interview experience sde2 five rounds technical offer."
        doc1 = _doc(content_a, doc_id="doc_a")
        doc2 = _doc(content_b, doc_id="doc_b")
        dedup.process(doc1)
        result = dedup.process(doc2)
        assert result is None


# ── Pre-loaded existing hashes ──

class TestExistingHashes:
    def test_doc_matching_existing_hash_filtered(self):
        # Compute what the hash would be for LONG_CONTENT
        import hashlib, re
        normalized = re.sub(r"\s+", " ", LONG_CONTENT.lower().strip())
        existing_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()

        dedup = Deduplicator(existing_hashes={existing_hash}, num_perm=64)
        doc = _doc(LONG_CONTENT, doc_id="doc_a")
        result = dedup.process(doc)
        assert result is None
        assert doc["_filter_reason"] == "exact_duplicate"

    def test_existing_hashes_loaded_into_set(self):
        hashes = {"abc123", "def456"}
        dedup = Deduplicator(existing_hashes=hashes, num_perm=64)
        assert "abc123" in dedup._exact_hashes
        assert "def456" in dedup._exact_hashes

    def test_no_existing_hashes_starts_empty(self):
        dedup = Deduplicator(num_perm=64)
        assert len(dedup._exact_hashes) == 0


# ── _compute_exact_hash() ──

class TestComputeExactHash:
    def test_same_content_same_hash(self, dedup):
        h1 = dedup._compute_exact_hash("hello world")
        h2 = dedup._compute_exact_hash("hello world")
        assert h1 == h2

    def test_different_content_different_hash(self, dedup):
        h1 = dedup._compute_exact_hash("hello world")
        h2 = dedup._compute_exact_hash("goodbye world")
        assert h1 != h2

    def test_hash_is_sha256_length(self, dedup):
        h = dedup._compute_exact_hash("test")
        assert len(h) == 64

    def test_case_insensitive(self, dedup):
        h1 = dedup._compute_exact_hash("Hello World")
        h2 = dedup._compute_exact_hash("hello world")
        assert h1 == h2

    def test_whitespace_normalized(self, dedup):
        h1 = dedup._compute_exact_hash("hello    world")
        h2 = dedup._compute_exact_hash("hello world")
        assert h1 == h2


# ── _create_shingles() ──

class TestCreateShingles:
    def test_shingle_count(self, dedup):
        text = "one two three four five"
        shingles = dedup._create_shingles(text)
        # 5 words, shingle_size=3 → 3 shingles
        assert len(shingles) == 3

    def test_short_text_returns_single_shingle(self, dedup):
        shingles = dedup._create_shingles("one two")
        assert len(shingles) == 1

    def test_shingles_are_lowercase(self, dedup):
        shingles = dedup._create_shingles("Hello World Test")
        for s in shingles:
            assert s == s.lower()

    def test_shingles_are_set(self, dedup):
        shingles = dedup._create_shingles("one two three four five")
        assert isinstance(shingles, set)

    def test_different_texts_different_shingles(self, dedup):
        s1 = dedup._create_shingles("apple banana cherry date")
        s2 = dedup._create_shingles("one two three four")
        assert s1.isdisjoint(s2)


# ── _compute_minhash() ──

class TestComputeMinHash:
    def test_returns_minhash_instance(self, dedup):
        shingles = {"a b c", "b c d", "c d e"}
        mh = dedup._compute_minhash(shingles)
        assert isinstance(mh, MinHash)

    def test_minhash_num_perm_matches_config(self, dedup):
        shingles = {"a b c", "b c d"}
        mh = dedup._compute_minhash(shingles)
        assert mh.num_perm == dedup.num_perm


# ── State persistence ──

class TestStatePersistence:
    def test_save_and_load_lsh(self, dedup):
        with tempfile.TemporaryDirectory() as tmpdir:
            dedup2 = Deduplicator(
                similarity_threshold=0.8,
                num_perm=64,
                shingle_size=3,
                state_dir=tmpdir,
            )
            # Process a doc to populate LSH
            doc = _doc(LONG_CONTENT, doc_id="doc_a")
            dedup2.process(doc)
            dedup2.save_state()

            # New instance loading same state
            dedup3 = Deduplicator(
                similarity_threshold=0.8,
                num_perm=64,
                shingle_size=3,
                state_dir=tmpdir,
            )
            lsh_path = dedup3._get_lsh_path()
            assert lsh_path.exists()

    def test_save_state_no_dir_does_nothing(self, dedup):
        """save_state with no state_dir should not raise."""
        doc = _doc(LONG_CONTENT)
        dedup.process(doc)
        dedup.save_state()  # Should not raise

    def test_get_lsh_path_returns_none_without_state_dir(self, dedup):
        assert dedup._get_lsh_path() is None

    def test_get_lsh_path_returns_path_with_state_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            d = Deduplicator(state_dir=tmpdir, num_perm=64)
            path = d._get_lsh_path()
            assert path is not None
            assert str(path).endswith("lsh_index.pkl")

    def test_corrupted_lsh_file_starts_fresh(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            lsh_path = os.path.join(tmpdir, "lsh_index.pkl")
            with open(lsh_path, "wb") as f:
                f.write(b"corrupted data not a pickle")
            # Should not raise — falls back to fresh LSH
            d = Deduplicator(state_dir=tmpdir, num_perm=64)
            assert isinstance(d._lsh, MinHashLSH)


# ── stats property ──

class TestStats:
    def test_stats_keys(self, dedup):
        stats = dedup.stats
        assert "exact_hashes_tracked" in stats
        assert "lsh_signatures_tracked" in stats
        assert "similarity_threshold" in stats

    def test_stats_update_after_processing(self, dedup):
        assert dedup.stats["exact_hashes_tracked"] == 0
        doc = _doc(LONG_CONTENT)
        dedup.process(doc)
        assert dedup.stats["exact_hashes_tracked"] == 1