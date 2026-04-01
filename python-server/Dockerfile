FROM python:3.12-slim AS builder

RUN pip install poetry==2.2.1
WORKDIR /app
COPY pyproject.toml poetry.lock ./
RUN poetry export -f requirements.txt -o requirements.txt --without-hashes


FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/service.py .

ENV SERVER_URL=http://localhost:8321
ENV STATE_DIR=/app/state

EXPOSE 8000

CMD ["python", "service.py"]
