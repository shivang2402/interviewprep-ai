"""
Hybrid retriever: vector + BM25 with Weighted Reciprocal Rank Fusion.
"""

import psycopg2
from sentence_transformers import SentenceTransformer


class HybridRetriever:
    def __init__(self, db_params: dict, retrieval_config: dict, model_info: dict):
        """
        Args:
            db_params: dict from config.get_db_params()
            retrieval_config: config["retrieval"] section
            model_info: dict from model_registry.get_deployed_embedding_model()
        """
        self.config = retrieval_config
        self.embedding_column = model_info["embedding_column"]
        self.model = SentenceTransformer(model_info["model_name"])
        self.conn = psycopg2.connect(**db_params)

    def _vector_search(self, query_embedding, top_k: int) -> list[tuple]:
        col = self.embedding_column
        # query = f"""
        #     SELECT chunk_id, chunk_text, source_url, company, role,
        #            1 - ({col} <=> %s::vector) AS similarity
        #     FROM document_chunks
        #     WHERE {col} IS NOT NULL
        #     ORDER BY {col} <=> %s::vector
        #     LIMIT %s;
        # """
        query = f"""
            SELECT dc.chunk_id, dc.chunk_text, pd.source_url, c.name  AS company, r.title AS role,
                1 - (dc.{col} <=> %s::vector) AS similarity
            FROM document_chunks dc
            JOIN processed_documents pd ON pd.document_id = dc.document_id
            JOIN interview_metadata im  ON im.document_id = dc.document_id
            JOIN companies c            ON c.company_id   = im.company_id
            JOIN roles r                ON r.role_id      = im.role_id
            WHERE dc.{col} IS NOT NULL
            ORDER BY dc.{col} <=> %s::vector
            LIMIT %s;
        """
        emb_list = query_embedding.tolist()
        with self.conn.cursor() as cur:
            cur.execute(query, (emb_list, emb_list, top_k))
            return cur.fetchall()

    def _bm25_search(self, query_text: str, top_k: int) -> list[tuple]:
        # query = """
        #     SELECT chunk_id, chunk_text, source_url, company, role,
        #            ts_rank_cd(chunk_tsvector, plainto_tsquery('english', %s)) AS rank
        #     FROM document_chunks
        #     WHERE chunk_tsvector @@ plainto_tsquery('english', %s)
        #     ORDER BY rank DESC
        #     LIMIT %s;
        # """
        query = f"""
          SELECT dc.chunk_id, dc.chunk_text, pd.source_url, c.name  AS company, r.title AS role,
            ts_rank_cd(
                to_tsvector('english', dc.chunk_text),
                plainto_tsquery('english', %s)
            ) AS rank
        FROM document_chunks dc
        JOIN processed_documents pd  ON pd.document_id = dc.document_id
        JOIN interview_metadata im   ON im.document_id = dc.document_id
        JOIN companies c             ON c.company_id   = im.company_id
        JOIN roles r                 ON r.role_id      = im.role_id
        WHERE to_tsvector('english', dc.chunk_text) @@ plainto_tsquery('english', %s)
        ORDER BY rank DESC
        LIMIT %s;
        """
        with self.conn.cursor() as cur:
            cur.execute(query, (query_text, query_text, top_k))
            return cur.fetchall()

    def _reciprocal_rank_fusion(self, vector_results, bm25_results, top_k: int) -> list[tuple]:
        k = self.config["rrf_k"]
        w_vec = self.config["vector_weight"]
        w_bm25 = self.config["bm25_weight"]
        scores = {}
        docs = {}

        for rank, row in enumerate(vector_results):
            doc_id = row[0]
            scores[doc_id] = scores.get(doc_id, 0) + w_vec / (k + rank + 1)
            docs[doc_id] = row

        for rank, row in enumerate(bm25_results):
            doc_id = row[0]
            scores[doc_id] = scores.get(doc_id, 0) + w_bm25 / (k + rank + 1)
            docs[doc_id] = row

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]
        return [docs[doc_id] for doc_id, _ in ranked]

    def retrieve(self, query: str, top_k: int = None) -> list[dict]:
        top_k = top_k or self.config["top_k"]
        fetch_k = top_k * self.config["fetch_multiplier"]

        query_embedding = self.model.encode(query)
        vector_results = self._vector_search(query_embedding, fetch_k)
        bm25_results = self._bm25_search(query, fetch_k)
        fused = self._reciprocal_rank_fusion(vector_results, bm25_results, top_k)

        return [
            {
                "id": row[0],
                "text": row[1],
                "source_url": row[2],
                "company": row[3],
                "role": row[4],
            }
            for row in fused
        ]

    def close(self):
        self.conn.close()