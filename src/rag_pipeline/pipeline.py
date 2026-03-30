"""
Entry point for the generation pipeline.
"""

from src.rag_pipeline.config  import load_generation_config, get_db_params
from src.rag_pipeline.model_registry import get_deployed_embedding_model
from src.rag_pipeline.retriever import HybridRetriever
from src.rag_pipeline.generator import RAGGenerator


def build_generator(config_path: str = None) -> RAGGenerator:
    """
    Wire up the full RAG pipeline from config + Vertex AI registry.
    Returns a ready-to-use RAGGenerator.
    """
    config = load_generation_config(config_path)
    db_params = get_db_params(config)
    model_info = get_deployed_embedding_model(config)

    retriever = HybridRetriever(
        db_params=db_params,
        retrieval_config=config["retrieval"],
        model_info=model_info,
    )

    return RAGGenerator(
        retriever=retriever,
        generation_config=config["generation"],
    )


if __name__ == "__main__":
    generator = build_generator()

    try:
        query = "How should I prepare for a Google software engineering interview?"
        result = generator.generate(query)

        print(f"Query: {result['query']}\n")
        print(f"Answer:\n{result['answer']}\n")
        print(f"Token usage: {result['usage']}")
        print(f"\nSources:")
        for i, chunk in enumerate(result["chunks"], 1):
            print(f"  [{i}] {chunk['company']} - {chunk['role']} ({chunk['source_url']})")
    finally:
        generator.close()