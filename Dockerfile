FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md /app/
COPY src /app/src
COPY scripts /app/scripts
COPY migrations /app/migrations

RUN pip install --no-cache-dir -e ".[postgres,mcp]"

EXPOSE 8080

CMD ["brainstem-api"]
