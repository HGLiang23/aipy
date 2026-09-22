# syntax=docker/dockerfile:1.7

ARG PYTHON_VERSION=3.12

FROM python:${PYTHON_VERSION}-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN groupadd --system --gid 10001 aipy \
    && useradd --system --uid 10001 --gid aipy --home-dir /app aipy

COPY pyproject.toml README.md ./
COPY src ./src
RUN python -m pip install .

# Copy application entry points and future migration assets that are not part of the package.
COPY . .

RUN chown -R aipy:aipy /app
USER aipy

FROM runtime AS api
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM runtime AS worker
CMD ["python", "-m", "celery", "-A", "apps.worker.celery_app:celery_app", "worker", "--loglevel=INFO"]

