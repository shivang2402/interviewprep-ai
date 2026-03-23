"""
InterviewPrep AI - Retrieval Model Evaluation Pipeline
======================================================
Eval dataset uses graded relevance scores:
    0 = NOT RELEVANT
    1 = PARTIALLY RELEVANT
    2 = HIGHLY RELEVANT

Components:
1. EvalDatasetLoader     - Loads eval queries from PostgreSQL (eval_queries_dataset)
2. RetrievalStrategy     - Pluggable: Vector, BM25, or Hybrid (RRF)
3. EvalRetriever         - Orchestrates query embedding + strategy execution
4. MetricsCalculator     - MRR@k, Recall@k, NDCG@k, Precision@k, score distributions
5. ExperimentRunner      - Single eval run with MLflow tracking
6. PipelineOrchestrator  - Runs all configs, logs comparison, applies decision gate
"""

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional
from collections import defaultdict
from enum import Enum

import numpy as np
import mlflow
import psycopg2
from sentence_transformers import SentenceTransformer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 1. Data Structures
# ---------------------------------------------------------------------------

@dataclass
class EvalQuery:
    """
    A single evaluation query with graded relevance judgments.

    relevance_grades: chunk_id -> grade (0, 1, or 2)
        Contains ALL judged chunks, including 0s (explicit negatives).
    relevant_chunk_ids: only chunks with grade >= relevance_threshold
    """
    query_id: int
    query_text: str
    category: str
    relevance_grades: dict[str, int]      # ALL judged chunks: chunk_id -> 0/1/2
    relevant_chunk_ids: list[str]          # chunks with grade >= threshold (for MRR/Recall)
    relevant_doc_ids: list[str]            # parallel to relevant_chunk_ids


@dataclass
class RetrievalResult:
    """Result from a single retrieval query."""
    query_id: int
    retrieved_chunk_ids: list[str]
    scores: list[float]


class RetrievalMode(str, Enum):
    VECTOR = "vector"
    BM25 = "bm25"
    HYBRID = "hybrid"


@dataclass
class BM25Config:
    """Configuration for BM25 text search."""
    search_column: str = "chunk_text"
    tsvector_column: str = "chunk_tsvector"
    search_language: str = "english"
    table: str = "document_chunks"
    chunk_id_column: str = "chunk_id"


@dataclass
class HybridConfig:
    """Configuration for hybrid retrieval (Weighted RRF)."""
    rrf_k: int = 60
    vector_weight: float = 0.5
    bm25_weight: float = 0.5
    vector_top_k: int = 30
    bm25_top_k: int = 30


@dataclass
class ModelConfig:
    """Full configuration for a single evaluation run."""
    model_name: str
    embedding_dim: int
    chunk_size: int
    overlap_size: int
    retrieval_mode: RetrievalMode = RetrievalMode.VECTOR
    # Relevance threshold: chunks with grade >= this count as "relevant"
    # for binary metrics (MRR, Recall, Precision). Default 1 means both
    # PARTIALLY and HIGHLY relevant chunks count.
    relevance_threshold: int = 1
    # Vector search config
    index_type: str = "hnsw"
    hnsw_m: int = 16
    hnsw_ef_construction: int = 64
    hnsw_ef_search: int = 100
    distance_metric: str = "cosine"
    embeddings_table: str = "document_chunks"
    model_name_column_value: str = ""
    # BM25 config
    bm25_config: BM25Config = field(default_factory=BM25Config)
    # Hybrid config
    hybrid_config: HybridConfig = field(default_factory=HybridConfig)

    def __post_init__(self):
        if not self.model_name_column_value:
            self.model_name_column_value = self.model_name

    @property
    def run_name(self) -> str:
        base = f"{self.model_name}_dim{self.embedding_dim}"
        if self.retrieval_mode == RetrievalMode.HYBRID:
            h = self.hybrid_config
            return f"{base}_hybrid_v{h.vector_weight}_b{h.bm25_weight}_rrf{h.rrf_k}"
        return f"{base}_{self.retrieval_mode.value}"

    def to_params_dict(self) -> dict:
        params = {
            "model_name": self.model_name,
            "embedding_dim": self.embedding_dim,
            "chunk_size": self.chunk_size,
            "overlap_size": self.overlap_size,
            "retrieval_mode": self.retrieval_mode.value,
            "relevance_threshold": self.relevance_threshold,
            "index_type": self.index_type,
            "hnsw_m": self.hnsw_m,
            "hnsw_ef_construction": self.hnsw_ef_construction,
            "hnsw_ef_search": self.hnsw_ef_search,
            "distance_metric": self.distance_metric,
        }
        if self.retrieval_mode in (RetrievalMode.BM25, RetrievalMode.HYBRID):
            params["bm25_search_language"] = self.bm25_config.search_language
            params["bm25_table"] = self.bm25_config.table
        if self.retrieval_mode == RetrievalMode.HYBRID:
            params["rrf_k"] = self.hybrid_config.rrf_k
            params["vector_weight"] = self.hybrid_config.vector_weight
            params["bm25_weight"] = self.hybrid_config.bm25_weight
            params["vector_top_k"] = self.hybrid_config.vector_top_k
            params["bm25_top_k"] = self.hybrid_config.bm25_top_k
        return params


# ---------------------------------------------------------------------------
# 2. Eval Dataset Loader
# ---------------------------------------------------------------------------

class EvalDatasetLoader:
    """
    Loads eval queries from eval_queries_dataset.
    Groups rows by query_id. Each row has a relevance_score (0, 1, or 2).
    Chunks with score=0 are kept as explicit negatives for NDCG and
    score distribution analysis.
    """

    LOAD_QUERY = """
        SELECT query_id, query_text, relevant_chunk_id, relevant_doc_id,
               query_category, relevance_score
        FROM eval_queries_dataset
        ORDER BY query_id, relevance_score DESC;
    """

    def __init__(self, db_conn, relevance_threshold: int = 1):
        self.conn = db_conn
        self.relevance_threshold = relevance_threshold

    def load(self) -> list[EvalQuery]:
        with self.conn.cursor() as cur:
            cur.execute(self.LOAD_QUERY)
            rows = cur.fetchall()

        grouped: dict[int, dict] = {}
        for query_id, query_text, chunk_id, doc_id, category, rel_score in rows:
            if query_id not in grouped:
                grouped[query_id] = {
                    "query_text": query_text,
                    "category": category,
                    "judgments": [],  # (chunk_id, doc_id, relevance_score)
                }
            grouped[query_id]["judgments"].append((chunk_id, doc_id, rel_score))

        queries = []
        for query_id, data in grouped.items():
            # All judged chunks with their grades (including 0s)
            relevance_grades = {c[0]: c[2] for c in data["judgments"]}

            # Only chunks meeting the threshold for binary metrics
            relevant = [(c[0], c[1]) for c in data["judgments"]
                        if c[2] >= self.relevance_threshold]
            relevant_chunk_ids = [r[0] for r in relevant]
            relevant_doc_ids = [r[1] for r in relevant]

            queries.append(EvalQuery(
                query_id=query_id,
                query_text=data["query_text"],
                category=data["category"],
                relevance_grades=relevance_grades,
                relevant_chunk_ids=relevant_chunk_ids,
                relevant_doc_ids=relevant_doc_ids,
            ))

        # Log dataset stats
        total_judgments = sum(len(q.relevance_grades) for q in queries)
        grade_counts = defaultdict(int)
        for q in queries:
            for g in q.relevance_grades.values():
                grade_counts[g] += 1

        logger.info(
            f"Loaded {len(queries)} eval queries with {total_judgments} total judgments | "
            f"Grade distribution: 0={grade_counts[0]}, 1={grade_counts[1]}, 2={grade_counts[2]} | "
            f"Relevance threshold >= {self.relevance_threshold}"
        )
        return queries


# ---------------------------------------------------------------------------
# 3. Retrieval Strategies
# ---------------------------------------------------------------------------

class RetrievalStrategy(ABC):
    @abstractmethod
    def retrieve(self, query_text: str, query_embedding: Optional[np.ndarray], k: int) -> tuple[list[str], list[float]]:
        ...


class VectorStrategy(RetrievalStrategy):
    def __init__(self, db_conn, config: ModelConfig):
        self.conn = db_conn
        self.config = config

    def retrieve(self, query_text: str, query_embedding: Optional[np.ndarray], k: int) -> tuple[list[str], list[float]]:
        if query_embedding is None:
            raise ValueError("VectorStrategy requires a query embedding")
        emb_list = query_embedding.tolist()
        sql = f"""
            SELECT chunk_id, 1 - (embedding <=> %s::vector) AS similarity
            FROM {self.config.embeddings_table}
            WHERE model_name = %s
            ORDER BY embedding <=> %s::vector
            LIMIT %s;
        """
        with self.conn.cursor() as cur:
            if self.config.index_type == "hnsw":
                cur.execute(f"SET hnsw.ef_search = {self.config.hnsw_ef_search};")
            cur.execute(sql, (emb_list, self.config.model_name_column_value, emb_list, k))
            rows = cur.fetchall()
        return [r[0] for r in rows], [float(r[1]) for r in rows]


class BM25Strategy(RetrievalStrategy):
    def __init__(self, db_conn, bm25_config: BM25Config):
        self.conn = db_conn
        self.bm25 = bm25_config

    def retrieve(self, query_text: str, query_embedding: Optional[np.ndarray], k: int) -> tuple[list[str], list[float]]:
        sql = f"""
            SELECT
                {self.bm25.chunk_id_column},
                ts_rank_cd({self.bm25.tsvector_column},
                           plainto_tsquery(%s, %s)) AS rank_score
            FROM {self.bm25.table}
            WHERE {self.bm25.tsvector_column} @@ plainto_tsquery(%s, %s)
            ORDER BY rank_score DESC
            LIMIT %s;
        """
        with self.conn.cursor() as cur:
            cur.execute(sql, (
                self.bm25.search_language, query_text,
                self.bm25.search_language, query_text,
                k,
            ))
            rows = cur.fetchall()
        return [r[0] for r in rows], [float(r[1]) for r in rows]


class HybridStrategy(RetrievalStrategy):
    """Weighted Reciprocal Rank Fusion of Vector + BM25."""

    def __init__(self, db_conn, config: ModelConfig):
        self.vector = VectorStrategy(db_conn, config)
        self.bm25 = BM25Strategy(db_conn, config.bm25_config)
        self.hybrid = config.hybrid_config

    def retrieve(self, query_text: str, query_embedding: Optional[np.ndarray], k: int) -> tuple[list[str], list[float]]:
        vec_ids, _ = self.vector.retrieve(query_text, query_embedding, self.hybrid.vector_top_k)
        bm25_ids, _ = self.bm25.retrieve(query_text, None, self.hybrid.bm25_top_k)

        vec_rank = {cid: rank for rank, cid in enumerate(vec_ids, start=1)}
        bm25_rank = {cid: rank for rank, cid in enumerate(bm25_ids, start=1)}
        all_ids = set(vec_ids) | set(bm25_ids)

        rrf_k = self.hybrid.rrf_k
        rrf_scores = {}
        for cid in all_ids:
            score = 0.0
            if cid in vec_rank:
                score += self.hybrid.vector_weight * (1.0 / (rrf_k + vec_rank[cid]))
            if cid in bm25_rank:
                score += self.hybrid.bm25_weight * (1.0 / (rrf_k + bm25_rank[cid]))
            rrf_scores[cid] = score

        ranked = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)[:k]
        return [cid for cid, _ in ranked], [score for _, score in ranked]


def build_strategy(db_conn, config: ModelConfig) -> RetrievalStrategy:
    if config.retrieval_mode == RetrievalMode.VECTOR:
        return VectorStrategy(db_conn, config)
    elif config.retrieval_mode == RetrievalMode.BM25:
        return BM25Strategy(db_conn, config.bm25_config)
    elif config.retrieval_mode == RetrievalMode.HYBRID:
        return HybridStrategy(db_conn, config)
    else:
        raise ValueError(f"Unknown retrieval mode: {config.retrieval_mode}")


# ---------------------------------------------------------------------------
# 4. Eval Retriever
# ---------------------------------------------------------------------------

class EvalRetriever:
    """Handles query embedding (when needed) and delegates to the strategy."""

    def __init__(self, db_conn, config: ModelConfig):
        self.conn = db_conn
        self.config = config
        self.strategy = build_strategy(db_conn, config)
        self._model: Optional[SentenceTransformer] = None
        self._needs_embedding = config.retrieval_mode in (RetrievalMode.VECTOR, RetrievalMode.HYBRID)

    def _load_model(self):
        if self._model is None and self._needs_embedding:
            logger.info(f"Loading embedding model: {self.config.model_name}")
            self._model = SentenceTransformer(self.config.model_name)
        return self._model

    def _embed_query(self, query_text: str) -> Optional[np.ndarray]:
        if not self._needs_embedding:
            return None
        model = self._load_model()
        return model.encode(query_text, normalize_embeddings=True)

    def retrieve(self, query: EvalQuery, k: int = 10) -> RetrievalResult:
        embedding = self._embed_query(query.query_text)
        chunk_ids, scores = self.strategy.retrieve(query.query_text, embedding, k)
        return RetrievalResult(
            query_id=query.query_id,
            retrieved_chunk_ids=chunk_ids,
            scores=scores,
        )

    def retrieve_all(self, queries: list[EvalQuery], k: int = 10) -> list[RetrievalResult]:
        results = []
        for i, query in enumerate(queries):
            results.append(self.retrieve(query, k))
            if (i + 1) % 10 == 0:
                logger.info(f"  Retrieved {i + 1}/{len(queries)} queries")
        return results


# ---------------------------------------------------------------------------
# 5. Metrics Calculator
# ---------------------------------------------------------------------------

class MetricsCalculator:
    """
    Retrieval quality metrics for graded relevance (0/1/2).

    Binary metrics (MRR, Recall, Precision) use a configurable relevance
    threshold: a chunk is "relevant" if its grade >= threshold.
    Default threshold=1 means both PARTIALLY and HIGHLY relevant count.

    NDCG uses the full graded scores directly — no thresholding.
    """

    K_VALUES = [1, 3, 5, 10]

    def __init__(self, relevance_threshold: int = 1):
        self.relevance_threshold = relevance_threshold

    # --- Primary Metrics ---

    def mrr_at_k(self, results: list[RetrievalResult], query_map: dict[int, EvalQuery], k: int) -> float:
        """
        Mean Reciprocal Rank @ k.
        First retrieved chunk with grade >= threshold determines the reciprocal rank.
        """
        rr_sum = 0.0
        for res in results:
            grades = query_map[res.query_id].relevance_grades
            for rank, cid in enumerate(res.retrieved_chunk_ids[:k], start=1):
                if grades.get(cid, 0) >= self.relevance_threshold:
                    rr_sum += 1.0 / rank
                    break
        return rr_sum / len(results) if results else 0.0

    def recall_at_k(self, results: list[RetrievalResult], query_map: dict[int, EvalQuery], k: int) -> float:
        """
        Recall @ k: fraction of relevant chunks (grade >= threshold) found in top-k.
        """
        recall_sum = 0.0
        count = 0
        for res in results:
            q = query_map[res.query_id]
            relevant = set(q.relevant_chunk_ids)  # already filtered by threshold
            if not relevant:
                continue
            retrieved_at_k = set(res.retrieved_chunk_ids[:k])
            recall_sum += len(relevant & retrieved_at_k) / len(relevant)
            count += 1
        return recall_sum / count if count else 0.0

    def precision_at_k(self, results: list[RetrievalResult], query_map: dict[int, EvalQuery], k: int) -> float:
        """
        Precision @ k: fraction of top-k results that are relevant (grade >= threshold).
        """
        precision_sum = 0.0
        for res in results:
            grades = query_map[res.query_id].relevance_grades
            top_k = res.retrieved_chunk_ids[:k]
            if not top_k:
                continue
            num_relevant = sum(1 for cid in top_k if grades.get(cid, 0) >= self.relevance_threshold)
            precision_sum += num_relevant / len(top_k)
        return precision_sum / len(results) if results else 0.0

    def ndcg_at_k(self, results: list[RetrievalResult], query_map: dict[int, EvalQuery], k: int) -> float:
        """
        NDCG @ k using full graded relevance (0/1/2).
        No thresholding — grade=1 contributes less gain than grade=2.
        """
        ndcg_sum = 0.0
        for res in results:
            grades = query_map[res.query_id].relevance_grades

            # DCG from retrieved ranking
            dcg = 0.0
            for rank, cid in enumerate(res.retrieved_chunk_ids[:k], start=1):
                rel = grades.get(cid, 0)
                dcg += (2**rel - 1) / np.log2(rank + 1)

            # Ideal DCG: sort ALL judged grades descending, take top-k
            ideal_rels = sorted(grades.values(), reverse=True)[:k]
            idcg = 0.0
            for rank, rel in enumerate(ideal_rels, start=1):
                idcg += (2**rel - 1) / np.log2(rank + 1)

            ndcg_sum += (dcg / idcg) if idcg > 0 else 0.0

        return ndcg_sum / len(results) if results else 0.0

    # --- Secondary Metrics ---

    def score_distribution_by_grade(
        self, results: list[RetrievalResult], query_map: dict[int, EvalQuery]
    ) -> tuple[dict, dict]:
        """
        Retrieval score distributions bucketed by relevance grade (0, 1, 2).
        For judged chunks: uses the known grade.
        For unjudged chunks (not in eval set): bucketed as "unjudged".

        Returns (flat_stats_dict, raw_distribution_dict).
        """
        buckets: dict[str, list[float]] = {"grade_0": [], "grade_1": [], "grade_2": [], "unjudged": []}

        for res in results:
            grades = query_map[res.query_id].relevance_grades
            for cid, score in zip(res.retrieved_chunk_ids, res.scores):
                if cid in grades:
                    buckets[f"grade_{grades[cid]}"].append(score)
                else:
                    buckets["unjudged"].append(score)

        flat_stats = {}
        for bucket_name, scores in buckets.items():
            prefix = f"score_{bucket_name}"
            if not scores:
                flat_stats[f"{prefix}_mean"] = 0.0
                flat_stats[f"{prefix}_count"] = 0
                continue
            arr = np.array(scores)
            flat_stats[f"{prefix}_mean"] = float(np.mean(arr))
            flat_stats[f"{prefix}_std"] = float(np.std(arr))
            flat_stats[f"{prefix}_median"] = float(np.median(arr))
            flat_stats[f"{prefix}_count"] = len(scores)

        # Separation gaps: how well does the retrieval score discriminate between grades?
        if buckets["grade_2"] and buckets["grade_0"]:
            flat_stats["separation_grade2_vs_grade0"] = (
                float(np.mean(buckets["grade_2"])) - float(np.mean(buckets["grade_0"]))
            )
        if buckets["grade_2"] and buckets["grade_1"]:
            flat_stats["separation_grade2_vs_grade1"] = (
                float(np.mean(buckets["grade_2"])) - float(np.mean(buckets["grade_1"]))
            )
        if buckets["grade_1"] and buckets["grade_0"]:
            flat_stats["separation_grade1_vs_grade0"] = (
                float(np.mean(buckets["grade_1"])) - float(np.mean(buckets["grade_0"]))
            )

        return flat_stats, buckets

    def storage_footprint_mb(self, db_conn, config: ModelConfig) -> float:
        if config.retrieval_mode == RetrievalMode.BM25:
            return 0.0
        with db_conn.cursor() as cur:
            cur.execute(
                f"SELECT COUNT(*) FROM {config.embeddings_table} WHERE model_name = %s",
                (config.model_name_column_value,),
            )
            count = cur.fetchone()[0]
        bytes_per_row = config.embedding_dim * 4 + 64
        return round((count * bytes_per_row) / (1024 * 1024), 2)

    # --- Per-Category Breakdown ---

    def per_category_metrics(
        self, results: list[RetrievalResult], query_map: dict[int, EvalQuery]
    ) -> dict[str, dict]:
        by_category: dict[str, list[RetrievalResult]] = defaultdict(list)
        for res in results:
            cat = query_map[res.query_id].category
            by_category[cat].append(res)

        breakdown = {}
        for cat, cat_results in by_category.items():
            cat_qmap = {r.query_id: query_map[r.query_id] for r in cat_results}
            cat_data = {"count": len(cat_results)}
            for k in self.K_VALUES:
                cat_data[f"mrr@{k}"] = round(self.mrr_at_k(cat_results, cat_qmap, k), 4)
                cat_data[f"recall@{k}"] = round(self.recall_at_k(cat_results, cat_qmap, k), 4)
                cat_data[f"precision@{k}"] = round(self.precision_at_k(cat_results, cat_qmap, k), 4)
                cat_data[f"ndcg@{k}"] = round(self.ndcg_at_k(cat_results, cat_qmap, k), 4)
            breakdown[cat] = cat_data

        return breakdown

    # --- Aggregate ---

    def compute_all(
        self, results: list[RetrievalResult], query_map: dict[int, EvalQuery],
        db_conn, config: ModelConfig,
    ) -> tuple[dict, dict]:
        """
        Returns (flat_metrics, artifacts).
        flat_metrics: for mlflow.log_metrics()
        artifacts: dicts to be saved as JSON artifacts
        """
        flat_metrics = {}

        # Primary metrics at all k values
        for k in self.K_VALUES:
            flat_metrics[f"mrr@{k}"] = round(self.mrr_at_k(results, query_map, k), 4)
            flat_metrics[f"recall@{k}"] = round(self.recall_at_k(results, query_map, k), 4)
            flat_metrics[f"precision@{k}"] = round(self.precision_at_k(results, query_map, k), 4)
            flat_metrics[f"ndcg@{k}"] = round(self.ndcg_at_k(results, query_map, k), 4)

        # Score distribution by grade
        score_stats, score_raw = self.score_distribution_by_grade(results, query_map)
        flat_metrics.update(score_stats)

        # Storage
        flat_metrics["storage_mb"] = self.storage_footprint_mb(db_conn, config)

        # Per-category breakdown
        category_breakdown = self.per_category_metrics(results, query_map)

        # Per-query detail for debugging
        per_query_detail = []
        for res in results:
            q = query_map[res.query_id]
            relevant = set(q.relevant_chunk_ids)
            # Grade of top-1 result (if judged)
            top1_grade = q.relevance_grades.get(
                res.retrieved_chunk_ids[0], -1
            ) if res.retrieved_chunk_ids else -1

            per_query_detail.append({
                "query_id": res.query_id,
                "query_text": q.query_text,
                "category": q.category,
                "num_judged": len(q.relevance_grades),
                "num_relevant": len(relevant),
                "grade_distribution": {
                    "highly_relevant": sum(1 for g in q.relevance_grades.values() if g == 2),
                    "partially_relevant": sum(1 for g in q.relevance_grades.values() if g == 1),
                    "not_relevant": sum(1 for g in q.relevance_grades.values() if g == 0),
                },
                "num_relevant_in_top10": len(set(res.retrieved_chunk_ids[:10]) & relevant),
                "top1_chunk_id": res.retrieved_chunk_ids[0] if res.retrieved_chunk_ids else None,
                "top1_grade": top1_grade,
                "top1_score": round(res.scores[0], 4) if res.scores else 0,
                "retrieved_grades": [
                    q.relevance_grades.get(cid, -1) for cid in res.retrieved_chunk_ids
                ],
                "retrieved_scores": [round(s, 4) for s in res.scores],
            })

        # Convert raw score lists for JSON serialization
        score_raw_serializable = {k: [round(s, 4) for s in v] for k, v in score_raw.items()}

        artifacts = {
            "category_breakdown": category_breakdown,
            "per_query_results": per_query_detail,
            "score_distribution_by_grade": score_raw_serializable,
        }

        return flat_metrics, artifacts


# ---------------------------------------------------------------------------
# 6. Selection Score
# ---------------------------------------------------------------------------

def compute_selection_score(metrics: dict) -> float:
    """
    Weighted score (latency excluded, weights redistributed):
    0.47 * NDCG@10 + 0.29 * Recall@10 + 0.18 * MRR@5 + 0.06 * (1/storage)
    """
    ndcg_10 = metrics.get("ndcg@10", 0)
    recall_10 = metrics.get("recall@10", 0)
    mrr_5 = metrics.get("mrr@5", 0)
    storage_mb = metrics.get("storage_mb", 60)
    storage_score = min(1.0, 120.0 / max(storage_mb, 1))

    return round(
        0.47 * ndcg_10 + 0.29 * recall_10 + 0.18 * mrr_5 + 0.06 * storage_score,
        4,
    )


# ---------------------------------------------------------------------------
# 7. Experiment Runner (Single Config)
# ---------------------------------------------------------------------------

class ExperimentRunner:
    """Runs full evaluation for one ModelConfig, logs to MLflow."""

    def __init__(self, db_conn, eval_queries: list[EvalQuery], relevance_threshold: int = 1):
        self.conn = db_conn
        self.queries = eval_queries
        self.query_map = {q.query_id: q for q in eval_queries}
        self.metrics_calc = MetricsCalculator(relevance_threshold=relevance_threshold)

    def run(self, config: ModelConfig, max_k: int = 10) -> dict:
        logger.info(f"{'='*60}")
        logger.info(f"Evaluating: {config.run_name}")
        logger.info(f"{'='*60}")

        retriever = EvalRetriever(self.conn, config)
        results = retriever.retrieve_all(self.queries, k=max_k)

        flat_metrics, artifacts = self.metrics_calc.compute_all(
            results, self.query_map, self.conn, config,
        )
        flat_metrics["selection_score"] = compute_selection_score(flat_metrics)

        self._log_to_mlflow(config, flat_metrics, artifacts)

        logger.info(
            f"Results: selection_score={flat_metrics['selection_score']:.4f} | "
            f"NDCG@10={flat_metrics['ndcg@10']:.4f} | "
            f"Recall@10={flat_metrics['recall@10']:.4f} | "
            f"Precision@10={flat_metrics['precision@10']:.4f} | "
            f"MRR@5={flat_metrics['mrr@5']:.4f}"
        )
        return flat_metrics

    def _log_to_mlflow(self, config: ModelConfig, metrics: dict, artifacts: dict):
        with mlflow.start_run(run_name=config.run_name):
            mlflow.log_params({
                **config.to_params_dict(),
                "num_eval_queries": len(self.queries),
            })

            mlflow.log_metrics(metrics)

            for name, data in artifacts.items():
                path = f"/tmp/{name}.json"
                with open(path, "w") as f:
                    json.dump(data, f, indent=2)
                mlflow.log_artifact(path, artifact_path="evaluation")

            mlflow.set_tag("model_family", config.model_name.split("/")[-1])
            mlflow.set_tag("retrieval_mode", config.retrieval_mode.value)
            mlflow.set_tag("eval_version", "v1")


# ---------------------------------------------------------------------------
# 8. Pipeline Orchestrator
# ---------------------------------------------------------------------------

class PipelineOrchestrator:
    """Runs eval across all configs, compares, applies decision gate."""

    def __init__(self, db_config: dict, mlflow_tracking_uri: str = "http://localhost:5000"):
        self.db_config = db_config
        self.mlflow_uri = mlflow_tracking_uri

    def run(self, configs: list[ModelConfig], relevance_threshold: int = 1) -> dict[str, dict]:
        mlflow.set_tracking_uri(self.mlflow_uri)
        mlflow.set_experiment("interviewprep-retrieval-eval")
        conn = psycopg2.connect(**self.db_config)

        loader = EvalDatasetLoader(conn, relevance_threshold=relevance_threshold)
        queries = loader.load()

        runner = ExperimentRunner(conn, queries, relevance_threshold=relevance_threshold)
        all_metrics: dict[str, dict] = {}

        for config in configs:
            try:
                metrics = runner.run(config)
                all_metrics[config.run_name] = metrics
            except Exception as e:
                logger.error(f"FAILED: {config.run_name} — {e}", exc_info=True)
                continue

        conn.close()
        self._log_comparison(all_metrics)
        return all_metrics

    def _log_comparison(self, all_metrics: dict[str, dict]):
        if not all_metrics:
            logger.warning("No configs completed evaluation.")
            return

        summary = sorted(
            [
                {"config": name, **{
                    k: v for k, v in m.items()
                    if k in ("selection_score", "ndcg@10", "recall@10", "precision@10", "mrr@5", "storage_mb")
                }}
                for name, m in all_metrics.items()
            ],
            key=lambda x: x["selection_score"],
            reverse=True,
        )

        with mlflow.start_run(run_name="model_comparison_summary"):
            path = "/tmp/model_comparison.json"
            with open(path, "w") as f:
                json.dump(summary, f, indent=2)
            mlflow.log_artifact(path, artifact_path="comparison")

            best = summary[0]
            mlflow.log_params({"best_config": best["config"]})
            mlflow.log_metrics({
                "best_selection_score": best["selection_score"],
                "best_ndcg@10": best["ndcg@10"],
            })

        self._apply_decision_gate(summary)

        logger.info(f"\n{'='*80}")
        logger.info("CONFIG COMPARISON (ranked by selection_score)")
        logger.info(f"{'='*80}")
        for i, s in enumerate(summary, 1):
            logger.info(
                f"  {i}. {s['config']:55s} | score={s['selection_score']:.4f} | "
                f"NDCG@10={s['ndcg@10']:.4f} | Recall@10={s['recall@10']:.4f} | "
                f"Precision@10={s['precision@10']:.4f}"
            )
        logger.info(f"{'='*80}")

    def _apply_decision_gate(self, summary: list[dict]):
        best_ndcg = summary[0]["ndcg@10"]
        if best_ndcg == 0:
            return
        openai_keywords = ["openai", "text-embedding"]
        for entry in summary:
            is_open_source = not any(kw in entry["config"].lower() for kw in openai_keywords)
            if is_open_source:
                gap = (best_ndcg - entry["ndcg@10"]) / best_ndcg
                if gap <= 0.05:
                    logger.info(
                        f"\n>>> DECISION GATE: Open-source config '{entry['config']}' is within "
                        f"{gap*100:.1f}% of best NDCG@10. RECOMMEND open-source. <<<"
                    )
                else:
                    logger.info(
                        f"\n>>> DECISION GATE: Best open-source '{entry['config']}' is "
                        f"{gap*100:.1f}% behind on NDCG@10 (>5% threshold). "
                        f"OpenAI model may be justified. <<<"
                    )
                break


# ---------------------------------------------------------------------------
# 9. Entry Point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    DB_CONFIG = {
        "host": "localhost",
        "port": 5432,
        "dbname": "interviewprep",
        "user": "postgres",
        "password": "",
    }

    bm25 = BM25Config(
        search_column="chunk_text",
        tsvector_column="chunk_tsvector",
        search_language="english",
        table="document_chunks",
        chunk_id_column="chunk_id",
    )

    CONFIGS = [
        # --- Pure Vector ---
        ModelConfig(
            model_name="sentence-transformers/all-MiniLM-L6-v2",
            embedding_dim=384, chunk_size=512, overlap_size=64,
            retrieval_mode=RetrievalMode.VECTOR,
        ),
        # ModelConfig(
        #     model_name="sentence-transformers/all-mpnet-base-v2",
        #     embedding_dim=768, chunk_size=512, overlap_size=64,
        #     retrieval_mode=RetrievalMode.VECTOR,
        # ),

        # --- Pure BM25 ---
        ModelConfig(
            model_name="bm25-baseline",
            embedding_dim=0, chunk_size=512, overlap_size=64,
            retrieval_mode=RetrievalMode.BM25,
            bm25_config=bm25,
        ),

        # --- Hybrid: MiniLM + BM25 ---
        ModelConfig(
            model_name="sentence-transformers/all-MiniLM-L6-v2",
            embedding_dim=384, chunk_size=512, overlap_size=64,
            retrieval_mode=RetrievalMode.HYBRID,
            bm25_config=bm25,
            hybrid_config=HybridConfig(
                rrf_k=60, vector_weight=0.5, bm25_weight=0.5,
                vector_top_k=30, bm25_top_k=30,
            ),
        ),

        # # --- Hybrid: mpnet + BM25 (equal weight) ---
        # ModelConfig(
        #     model_name="sentence-transformers/all-mpnet-base-v2",
        #     embedding_dim=768, chunk_size=512, overlap_size=64,
        #     retrieval_mode=RetrievalMode.HYBRID,
        #     bm25_config=bm25,
        #     hybrid_config=HybridConfig(
        #         rrf_k=60, vector_weight=0.5, bm25_weight=0.5,
        #         vector_top_k=30, bm25_top_k=30,
        #     ),
        # ),

        # # --- Hybrid: mpnet + BM25 (vector-heavy) ---
        # ModelConfig(
        #     model_name="sentence-transformers/all-mpnet-base-v2",
        #     embedding_dim=768, chunk_size=512, overlap_size=64,
        #     retrieval_mode=RetrievalMode.HYBRID,
        #     bm25_config=bm25,
        #     hybrid_config=HybridConfig(
        #         rrf_k=60, vector_weight=0.7, bm25_weight=0.3,
        #         vector_top_k=30, bm25_top_k=30,
        #     ),
        # ),
    ]

    # Run with threshold=1: both PARTIALLY and HIGHLY relevant count for binary metrics
    orchestrator = PipelineOrchestrator(DB_CONFIG)
    results = orchestrator.run(CONFIGS, relevance_threshold=1)

    # Optional: re-run with threshold=2 to see metrics when only HIGHLY relevant counts
    # results_strict = orchestrator.run(CONFIGS, relevance_threshold=2)