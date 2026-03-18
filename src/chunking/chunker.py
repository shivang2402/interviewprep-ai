import re
import uuid
from pathlib import Path
from typing import Optional

import yaml

from src.data_models.document_chunk import DocumentChunk

# ---------------------------------------------------------------------------
# Load config
# ---------------------------------------------------------------------------

def _load_config() -> dict:
    path = Path(__file__).parent / "chunking_config.yaml"
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _compile_round_regex(patterns: list[str]) -> re.Pattern:
    inner = "|".join(patterns)
    return re.compile(
        rf"(?:^|\n)\s*(?:{inner})", re.IGNORECASE | re.MULTILINE
    )


_cfg = _load_config()

CHUNK_SIZE_WORDS = _cfg["chunking"]["chunk_size_words"]
OVERLAP_WORDS    = _cfg["chunking"]["overlap_words"]
MIN_DOC_WORDS    = _cfg["chunking"]["min_doc_words"]
ROUND_RE         = _compile_round_regex(_cfg["round_boundary_patterns"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def wc(text: str) -> int:
    return len(text.split())


def split_sentences(text: str) -> list[str]:
    parts = re.split(r'(?<=[.!?])\s+', text.strip())
    return [p for p in parts if p.strip()]


def char_offset(full_text: str, segment: str) -> tuple[int, int]:
    idx = full_text.find(segment)
    if idx == -1:
        return 0, len(segment)
    return idx, idx + len(segment)


def get_round_label(text: str, match) -> str:
    """
    Capture the full round header line.
    match.start() points to the newline BEFORE the label — skip past it.
    """
    start = match.start()
    while start < len(text) and text[start] in ('\n', '\r', ' ', '\t'):
        start += 1
    line_end = text.find("\n", start)
    line = text[start: line_end if line_end != -1 else start + 80]
    return line.strip()[:60]


def build_header(
    company:      Optional[str],
    role:         Optional[str],
    round_label:  Optional[str],
    chunk_index:  int,
    total_chunks: int,
) -> str:
    """
    Context prefix prepended to every chunk before embedding.
    Format: Company: X | Role: Y | Round: Z | Part: 1 of 4 |
    """
    parts = []
    if company:
        parts.append(f"Company: {company}")
    if role:
        parts.append(f"Role: {role}")
    if round_label:
        parts.append(f"Round: {round_label}")
    parts.append(f"Part: {chunk_index + 1} of {total_chunks}")
    return " | ".join(parts) + " | "


# ---------------------------------------------------------------------------
# Fixed window splitter
# ---------------------------------------------------------------------------

def fixed_window_split(text: str) -> list[str]:
    """
    Split text into <=500-word windows at sentence boundaries
    with 50-word overlap carried over from the previous window.
    """
    sentences = split_sentences(text)
    windows, current, cur_wc = [], [], 0

    for sent in sentences:
        swc = wc(sent)
        if cur_wc + swc > CHUNK_SIZE_WORDS and current:
            windows.append(" ".join(current))
            overlap, ov_wc = [], 0
            for s in reversed(current):
                if ov_wc + wc(s) <= OVERLAP_WORDS:
                    overlap.insert(0, s)
                    ov_wc += wc(s)
                else:
                    break
            current, cur_wc = overlap, ov_wc
        current.append(sent)
        cur_wc += swc

    if current:
        windows.append(" ".join(current))

    return windows


# ---------------------------------------------------------------------------
# Structural splitter
# ---------------------------------------------------------------------------

def structural_split(text: str) -> list[tuple[Optional[str], str]]:
    """
    Split text at round boundary markers.
    Returns list of (round_label, segment_text).
    Each segment is one round — no merging.
    """
    matches = list(ROUND_RE.finditer(text))
    if not matches:
        return [(None, text)]

    segments = []

    preamble = text[:matches[0].start()].strip()
    if preamble:
        segments.append(("Preamble", preamble))

    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        seg = text[m.start():end].strip()
        label = get_round_label(text, m)
        if seg:
            segments.append((label, seg))

    return segments


# ---------------------------------------------------------------------------
# Strategy detector
# ---------------------------------------------------------------------------

def detect_strategy(text: str) -> str:
    if wc(text) < MIN_DOC_WORDS:
        return "single_chunk"
    if ROUND_RE.search(text):
        return "structural"
    return "fixed_window"


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def chunk_document(
    document_id:       str,
    cleaned_content:   str,
    source_platform:   str,
    company:           Optional[str] = None,
    role:              Optional[str] = None,
    experience_level:  Optional[str] = None,
    interview_outcome: Optional[str] = None,
    difficulty:        Optional[str] = None,
    interview_type:    Optional[str] = None,
    topics:            Optional[list[str]] = None,
) -> list[DocumentChunk]:

    topics    = topics or []
    full_text = cleaned_content.strip().replace("\r\n", "\n").replace("\r", "\n")
    strategy  = detect_strategy(full_text)

    raw_segments: list[tuple[Optional[str], str]] = []

    if strategy == "single_chunk":
        raw_segments = [(None, full_text)]

    elif strategy == "structural":
        for label, seg in structural_split(full_text):
            if wc(seg) <= CHUNK_SIZE_WORDS:
                raw_segments.append((label, seg))
            else:
                for j, sub in enumerate(fixed_window_split(seg)):
                    part_label = f"{label} (part {j + 1})" if label else f"part {j + 1}"
                    raw_segments.append((part_label, sub))

    else:
        for sub in fixed_window_split(full_text):
            raw_segments.append((None, sub))

    # Keep all segments including short ones — every round is meaningful
    total  = len(raw_segments)
    chunks = []

    for idx, (round_label, raw) in enumerate(raw_segments):
        header     = build_header(company, role, round_label, idx, total)
        chunk_text = header + raw
        cs, ce     = char_offset(full_text, raw)

        chunks.append(DocumentChunk(
            chunk_id          = str(uuid.uuid4()),
            document_id       = document_id,
            chunk_index       = idx,
            total_chunks      = total,
            chunk_text        = chunk_text,
            raw_text          = raw,
            word_count        = wc(raw),
            char_start_offset = cs,
            char_end_offset   = ce,
            strategy          = strategy,
            round_label=round_label
        ))

    return chunks


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_chunks(chunks: list[DocumentChunk]) -> dict:
    report = {"total": len(chunks), "warnings": [], "errors": []}

    for c in chunks:
        if not c.document_id:
            report["errors"].append(f"{c.chunk_id}: missing document_id")
        if c.word_count > CHUNK_SIZE_WORDS + OVERLAP_WORDS:
            report["warnings"].append(f"chunk {c.chunk_index}: word_count={c.word_count} exceeds max")
        if c.company and f"Company: {c.company}" not in c.chunk_text:
            report["warnings"].append(f"chunk {c.chunk_index}: header missing company")
        expected_part = f"Part: {c.chunk_index + 1} of {c.total_chunks}"
        if expected_part not in c.chunk_text:
            report["warnings"].append(f"chunk {c.chunk_index}: header missing part label")

    assert not report["errors"], f"Validation failed: {report['errors']}"
    return report