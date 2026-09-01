FROM python:3.12-slim

ARG INSTALL_AI=true
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src ./src

RUN if [ "$INSTALL_AI" = "true" ]; then pip install --no-cache-dir ".[ai]"; else pip install --no-cache-dir .; fi

RUN addgroup --system app && adduser --system --ingroup app app \
    && mkdir -p /data/uploads /data/artifacts /data/indexes /data/models \
    && chown -R app:app /app /data

USER app
EXPOSE 8000
CMD ["uvicorn", "listen_dragon.main:app", "--host", "0.0.0.0", "--port", "8000"]
