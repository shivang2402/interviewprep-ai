from dataclasses import dataclass
from typing import Optional

@dataclass
class DocumentChunk:
    chunk_id:          str
    document_id:       str
    chunk_index:       int
    total_chunks:      int
    chunk_text:        str       # header + raw_text → sent to embedder
    raw_text:          str       # content only      → shown to user
    word_count:        int
    char_start_offset: int
    char_end_offset:   int
    strategy:          str
    round_label: Optional[str] = None