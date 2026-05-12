FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV SGE_DATA_DIR=/app/data
ENV SGE_CHROMA_DIR=/app/data/chroma

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

COPY data/chroma ./data/chroma

EXPOSE 8000

CMD ["sh", "-c", "uvicorn sge_rag.api:app --host 0.0.0.0 --port ${PORT:-8000}"]
