import os
os.environ["USE_TF"] = "0"
os.environ["TRANSFORMERS_NO_TF"] = "1"

import sys
import logging

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from routers import chat

load_dotenv()

# Allow importing from project root so src.rag_pipeline is accessible
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="InterviewPrep AI API", version="2.0.0")

origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in origins],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat.router, prefix="/api")


@app.on_event("startup")
def startup():
    # Ensure monitoring table exists
    chat.ensure_log_table()

    try:
        from src.rag_pipeline.pipeline import build_generator

        generator = build_generator()
        chat.set_generator(generator)
        logger.info("RAG pipeline initialized successfully")
    except Exception:
        logger.exception("Failed to initialize RAG pipeline")


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "rag_ready": chat._generator is not None,
    }


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error"},
    )
