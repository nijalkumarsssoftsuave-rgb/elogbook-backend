# Engineering Code Standards, discipline 4: containerised runtime.
# Base image pinned by tag; in the air-gapped environment it is pulled by digest
# through the sanctioned scanned mirror (Outstanding Items Tracker A-03).
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# --- dependencies ---
COPY pyproject.toml ./
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir .

# --- application ---
COPY src ./src

# non-root runtime
RUN useradd --create-home --uid 10001 appuser
USER appuser

EXPOSE 8000

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
