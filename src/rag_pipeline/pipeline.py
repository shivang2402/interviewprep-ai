"""
Entry point for the generation pipeline.
"""
from src.rag_pipeline.model_registry import get_deployed_embedding_model
from src.rag_pipeline.retriever import HybridRetriever
from src.rag_pipeline.generator import RAGGenerator

from pathlib import Path
import yaml


CONFIG_PATH = Path(__file__).resolve().parents[0] / "config.yaml"


def load_generation_config(path: str = None) -> dict:
    config_file = Path(path) if path else CONFIG_PATH
    with open(config_file) as f:
        return yaml.safe_load(f)


def get_db_params(config: dict) -> dict:
    db = config["database"]
    return {
        "host": db["host"],
        "port": db["port"],
        "dbname": db["dbname"],
        "user": db["user"],
        "password": db["password"],
    }


def build_generator(config_path: str = None) -> RAGGenerator:
    """
    Wire up the full RAG pipeline from config + Vertex AI registry.
    Returns a ready-to-use RAGGenerator.
    """
    config = load_generation_config(config_path)
    db_params = get_db_params(config)
    model_info = get_deployed_embedding_model(config)
    print(model_info)

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
        query = "I need help to prepare with SRE interview at Nutanix?"
        result = generator.generate(query)

        print(result)
        print("\n\n\n")
        print(f"Query: {result['query']}\n")
        print(f"Answer:\n{result['answer']}\n")
        # print(f"Token usage: {result['usage']}")
        # print(f"\nSources:")
        # for i, chunk in enumerate(result["chunks"], 1):
        #     print(f"  [{i}] {chunk['company']} - {chunk['role']} ({chunk['source_url']})")
    finally:
        generator.close()