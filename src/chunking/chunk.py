import re
import uuid
from typing import Optional
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

CHUNK_SIZE_WORDS = 500
OVERLAP_WORDS    = 50
MIN_DOC_WORDS    = 150


# ---------------------------------------------------------------------------
# Pydantic schema
# ---------------------------------------------------------------------------

class DocumentChunk(BaseModel):
    chunk_id:          str
    document_id:       str
    chunk_index:       int
    total_chunks:      int
    chunk_text:        str       # header + raw_text → sent to embedder
    raw_text:          str       # content only      → shown to user
    word_count:        int
    char_start_offset: int
    char_end_offset:   int
    round_label:       Optional[str] = None
    strategy:          str
    source_platform:   str
    company:           Optional[str] = None
    role:              Optional[str] = None
    experience_level:  Optional[str] = None
    interview_outcome: Optional[str] = None
    difficulty:        Optional[str] = None
    interview_type:    Optional[str] = None
    topics:            list[str] = []


# ---------------------------------------------------------------------------
# Round boundary regex
# ---------------------------------------------------------------------------

ROUND_RE = re.compile(
    r"(?:^|\n)\s*"
    r"(?:"
    r"(?:round|interview\s*round)[\s\-]*(?:\d+(?:\s*(?:&|and)\s*\d+)?|[IVXL]+)\s*(?:[:\-\(]|\([^)]*\)\s*:)?"
    r"|(?:zero|first|second|third|fourth|fifth|sixth|seventh)\s*round\s*[:\-\(]?"
    r"|(?:hr|human\s*resource)\s*(?:round|interview)\s*[:\-\(]?"
    r"|phone\s*(?:screen|interview)\s*[:\-\(]?"
    r"|online\s*(?:assessment|test)\s*[:\-\(]?"
    r"|(?:oa|written\s*test|aptitude\s*test)\s*[:\-\(]"
    r"|technical\s*(?:round|interview)\s*\d*\s*[:\-\(]?"
    r"|coding\s*(?:round|interview)\s*\d*\s*[:\-\(]?"
    r"|system\s*design\s*(?:round|interview)?\s*[:\-\(]?"
    r"|machine\s*coding\s*(?:round)?\s*[:\-\(]?"
    r"|behavioral\s*(?:round|interview)\s*[:\-\(]?"
    r"|managerial\s*(?:round|interview)\s*[:\-\(]?"
    r"|final\s*(?:round|interview)\s*[:\-\(]?"
    r"|onsite\s*(?:round|interview)?\s*[:\-\(]?"
    r"|group\s*discussion\s*[:\-\(]?"
    r"|superday\s*(?:round|rounds)?\s*[:\-\(]?"
    r"|f2f\s*\d+\s*[:\-]?"
    r"|f\s*2\s*f\s*\d+\s*[:\-]?"
    r")",
    re.IGNORECASE | re.MULTILINE,
)


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
            round_label       = round_label,
            strategy          = strategy,
            source_platform   = source_platform,
            company           = company,
            role              = role,
            experience_level  = experience_level,
            interview_outcome = interview_outcome,
            difficulty        = difficulty,
            interview_type    = interview_type,
            topics            = topics,
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