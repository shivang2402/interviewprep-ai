"""SQL query strings for processed_documents and interview_metadata."""

UPSERT_PROCESSED_DOC = """
INSERT INTO public.processed_documents (
    document_id, source_platform, source_url, content_hash,
    title, cleaned_content, word_count,
    published_at, scraped_at, processed_at,
    scrape_batch_id, source_metadata
)
VALUES (
    %(document_id)s,
    %(source_platform)s::public.source_platform_enum,
    %(source_url)s,
    %(content_hash)s,
    %(title)s,
    %(content)s,
    %(word_count)s,
    %(published_at)s,
    %(scraped_at)s,
    %(preprocessed_at)s,
    %(scrape_batch_id)s,
    %(source_metadata)s::jsonb
)
ON CONFLICT (document_id) DO UPDATE SET
    content_hash    = EXCLUDED.content_hash,
    cleaned_content = EXCLUDED.cleaned_content,
    word_count      = EXCLUDED.word_count,
    processed_at    = EXCLUDED.processed_at,
    source_metadata = EXCLUDED.source_metadata;
"""

UPSERT_INTERVIEW_META = """
INSERT INTO public.interview_metadata (
    document_id, company_id, role_id,
    experience_level, interview_outcome, difficulty,
    num_rounds, interview_type, topics
)
VALUES (
    %(document_id)s,
    %(company_id)s,
    %(role_id)s,
    %(experience_level)s::public.experience_level_enum,
    %(interview_outcome)s::public.interview_outcome_enum,
    %(difficulty)s::public.difficulty_enum,
    %(num_rounds)s,
    %(interview_type)s::public.interview_type_enum,
    %(topics)s::text[]
)
ON CONFLICT (document_id) DO UPDATE SET
    company_id         = EXCLUDED.company_id,
    role_id            = EXCLUDED.role_id,
    experience_level   = EXCLUDED.experience_level,
    interview_outcome  = EXCLUDED.interview_outcome,
    difficulty         = EXCLUDED.difficulty,
    num_rounds         = EXCLUDED.num_rounds,
    interview_type     = EXCLUDED.interview_type,
    topics             = EXCLUDED.topics;
"""
