FROM python:3.12-slim

RUN pip install --no-cache-dir uv
# in your Dockerfile, after pip install
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

WORKDIR /app

# Install dependencies using the lockfile (cached layer — rebuild only when deps change)
COPY pyproject.toml uv.lock ./

RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH"

# graph.ttl must be pre-built before docker build (run ingest.py first)
COPY . ./backend/

EXPOSE 8000

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
