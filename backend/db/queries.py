LIST_DOCUMENTS = """
SELECT
    pd.document_id,
    pd.source_platform,
    pd.source_url,
    pd.title,
    pd.word_count,
    pd.published_at,
    pd.scraped_at,
    c.name AS company,
    r.title AS role,
    im.experience_level,
    im.interview_outcome,
    im.difficulty,
    im.interview_type,
    im.topics,
    im.num_rounds
FROM public.processed_documents pd
LEFT JOIN public.interview_metadata im ON pd.document_id = im.document_id
LEFT JOIN public.companies c ON im.company_id = c.company_id
LEFT JOIN public.roles r ON im.role_id = r.role_id
WHERE 1=1
"""

GET_DOCUMENT = """
SELECT
    pd.document_id,
    pd.source_platform,
    pd.source_url,
    pd.content_hash,
    pd.title,
    pd.cleaned_content,
    pd.word_count,
    pd.published_at,
    pd.scraped_at,
    pd.processed_at,
    pd.scrape_batch_id,
    pd.source_metadata,
    c.name AS company,
    r.title AS role,
    im.experience_level,
    im.interview_outcome,
    im.difficulty,
    im.interview_type,
    im.topics,
    im.num_rounds
FROM public.processed_documents pd
LEFT JOIN public.interview_metadata im ON pd.document_id = im.document_id
LEFT JOIN public.companies c ON im.company_id = c.company_id
LEFT JOIN public.roles r ON im.role_id = r.role_id
WHERE pd.document_id = %s
"""

GET_DOCUMENT_CHUNKS = """
SELECT
    chunk_id,
    document_id,
    chunk_index,
    total_chunks,
    chunk_text,
    raw_text,
    word_count,
    char_start_offset,
    char_end_offset,
    strategy,
    round_label
FROM public.document_chunks
WHERE document_id = %s
ORDER BY chunk_index
"""

FULLTEXT_SEARCH = """
SELECT
    pd.document_id,
    pd.source_platform,
    pd.title,
    pd.word_count,
    pd.published_at,
    c.name AS company,
    r.title AS role,
    im.difficulty,
    im.interview_outcome,
    ts_rank(
        to_tsvector('english', coalesce(pd.title,'') || ' ' || coalesce(pd.cleaned_content,'')),
        plainto_tsquery('english', %s)
    ) AS rank,
    ts_headline(
        'english',
        pd.cleaned_content,
        plainto_tsquery('english', %s),
        'StartSel=**, StopSel=**, MaxWords=60, MinWords=20'
    ) AS snippet
FROM public.processed_documents pd
LEFT JOIN public.interview_metadata im ON pd.document_id = im.document_id
LEFT JOIN public.companies c ON im.company_id = c.company_id
LEFT JOIN public.roles r ON im.role_id = r.role_id
WHERE to_tsvector('english', coalesce(pd.title,'') || ' ' || coalesce(pd.cleaned_content,''))
      @@ plainto_tsquery('english', %s)
"""

SEMANTIC_SEARCH = """
SELECT
    dc.chunk_id,
    dc.document_id,
    dc.raw_text,
    dc.chunk_index,
    dc.total_chunks,
    dc.round_label,
    dc.word_count,
    pd.title,
    pd.source_platform,
    c.name AS company,
    r.title AS role,
    im.difficulty,
    im.interview_outcome,
    1 - (dc.embeddings_all_minilm_l6_v2 <=> %s::vector) AS similarity
FROM public.document_chunks dc
JOIN public.processed_documents pd ON dc.document_id = pd.document_id
LEFT JOIN public.interview_metadata im ON pd.document_id = im.document_id
LEFT JOIN public.companies c ON im.company_id = c.company_id
LEFT JOIN public.roles r ON im.role_id = r.role_id
WHERE dc.embeddings_all_minilm_l6_v2 IS NOT NULL
"""

STATS_OVERVIEW = """
SELECT
    (SELECT COUNT(*) FROM public.processed_documents) AS total_documents,
    (SELECT COUNT(*) FROM public.companies) AS total_companies,
    (SELECT COUNT(*) FROM public.roles) AS total_roles
"""

STATS_PLATFORM_BREAKDOWN = """
SELECT source_platform, COUNT(*) AS count
FROM public.processed_documents
GROUP BY source_platform
ORDER BY count DESC
"""

STATS_COMPANIES = """
SELECT c.name AS company, COUNT(*) AS document_count
FROM public.interview_metadata im
JOIN public.companies c ON im.company_id = c.company_id
GROUP BY c.name
ORDER BY document_count DESC
"""

STATS_TOPICS = """
SELECT topic, COUNT(*) AS frequency
FROM public.interview_metadata, unnest(topics) AS topic
GROUP BY topic
ORDER BY frequency DESC
"""

STATS_OUTCOMES = """
SELECT
    COALESCE(interview_outcome::text, 'unknown') AS outcome,
    COUNT(*) AS count
FROM public.interview_metadata
GROUP BY interview_outcome
ORDER BY count DESC
"""

FILTER_PLATFORMS = """
SELECT DISTINCT source_platform FROM public.processed_documents ORDER BY source_platform
"""

FILTER_COMPANIES = """
SELECT DISTINCT c.name
FROM public.interview_metadata im
JOIN public.companies c ON im.company_id = c.company_id
ORDER BY c.name
"""

FILTER_ROLES = """
SELECT DISTINCT r.title
FROM public.interview_metadata im
JOIN public.roles r ON im.role_id = r.role_id
ORDER BY r.title
"""

FILTER_DIFFICULTIES = """
SELECT DISTINCT difficulty::text
FROM public.interview_metadata
WHERE difficulty IS NOT NULL
ORDER BY difficulty::text
"""

FILTER_OUTCOMES = """
SELECT DISTINCT interview_outcome::text
FROM public.interview_metadata
WHERE interview_outcome IS NOT NULL
ORDER BY interview_outcome::text
"""
