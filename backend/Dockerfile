FROM python:3.12-slim

RUN pip install --no-cache-dir uv

WORKDIR /app

# Install dependencies using the lockfile (cached layer — rebuild only when deps change)
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH"

COPY backend/ ./backend/
COPY src/content/recipes/ ./src/content/recipes/

# graph.ttl must be pre-built before docker build — see docker-compose.yml
COPY backend/graph.ttl ./

EXPOSE 8000

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
