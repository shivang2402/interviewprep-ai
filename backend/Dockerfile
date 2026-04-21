# ── Stage 1: Install Python dependencies ──
FROM python:3.11-slim AS builder

WORKDIR /app

COPY backend/requirements.txt ./backend/requirements.txt
COPY requirements.txt ./requirements.txt

RUN pip install --no-cache-dir --prefix=/install \
    -r backend/requirements.txt \
    -r requirements.txt

# ── Stage 2: Production image ──
FROM python:3.11-slim

WORKDIR /app

COPY --from=builder /install /usr/local

# Copy backend application code
COPY backend/ ./backend/

# Copy src/ (needed by backend/main.py for src.rag_pipeline imports)
COPY src/ ./src/

# Disable TensorFlow to save memory
ENV USE_TF=0
ENV TRANSFORMERS_NO_TF=1
ENV HF_HOME=/app/hf_cache
ENV SENTENCE_TRANSFORMERS_HOME=/app/hf_cache
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Pre-download the sentence-transformers model at build time
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

# Force offline mode — never contact HuggingFace at runtime
ENV HF_HUB_OFFLINE=1

WORKDIR /app/backend

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
