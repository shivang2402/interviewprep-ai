"""
RAG Generator — orchestrates retrieval + OpenAI generation.
"""

# from openai import OpenAI
# from src.rag_pipeline.prompt import build_messages
import os
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI
from src.rag_pipeline.prompt import build_messages

_env_path = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(dotenv_path=_env_path)


class RAGGenerator:
    def __init__(self, retriever, generation_config: dict):
        """
        Args:
            retriever: HybridRetriever instance
            generation_config: config["generation"] section
        """
        self.retriever = retriever
        self.config = generation_config
        self.client = OpenAI()  # uses OPENAI_API_KEY env var

    def generate(self, query: str, top_k: int = None) -> dict:
        # 1. Retrieve
        chunks = self.retriever.retrieve(query, top_k=top_k)

        # 2. Build prompt
        messages = build_messages(query, chunks)

        # 3. Call OpenAI
        response = self.client.chat.completions.create(
            model=self.config["openai_model"],
            messages=messages,
            temperature=self.config["temperature"],
            max_tokens=self.config["max_tokens"],
        )

        answer = response.choices[0].message.content
        usage = response.usage

        return {
            "query": query,
            "answer": answer,
            "chunks": chunks,
            "model": self.config["openai_model"],
            "usage": {
                "prompt_tokens": usage.prompt_tokens,
                "completion_tokens": usage.completion_tokens,
                "total_tokens": usage.total_tokens,
            },
        }

    def close(self):
        self.retriever.close()