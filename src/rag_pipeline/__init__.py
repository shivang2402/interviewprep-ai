def __getattr__(name):
    if name == "RAGGenerator":
        from src.rag_pipeline.generator import RAGGenerator
        return RAGGenerator
    if name == "HybridRetriever":
        from src.rag_pipeline.retriever import HybridRetriever
        return HybridRetriever
    if name == "build_generator":
        from src.rag_pipeline.pipeline import build_generator
        return build_generator
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = ["RAGGenerator", "HybridRetriever", "build_generator"]