import logging

from fastapi import APIRouter, HTTPException

from models.schemas import ChatRequest, ChatResponse, ChatSource, TokenUsage

logger = logging.getLogger(__name__)

router = APIRouter()

# Populated by main.py on startup
_generator = None


def set_generator(generator):
    global _generator
    _generator = generator


@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    if _generator is None:
        raise HTTPException(status_code=503, detail="RAG pipeline not initialized")

    try:
        result = _generator.generate(req.message)
    except Exception:
        logger.exception("RAG generation failed")
        raise HTTPException(status_code=500, detail="Failed to generate response")

    sources = [
        ChatSource(
            company=chunk.get("company"),
            role=chunk.get("role"),
            source_url=chunk.get("source_url"),
        )
        for chunk in result.get("chunks", [])
    ]

    return ChatResponse(
        answer=result["answer"],
        sources=sources,
        usage=TokenUsage(**result["usage"]),
    )
