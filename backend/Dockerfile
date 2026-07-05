# syntax=docker/dockerfile:1
# System deps + Playwright chromium are in the base image (rarely changes).
# Build base: docker build -f backend/Dockerfile.playwright-base -t rapport-playwright-base:latest backend/
FROM rapport-playwright-base:latest

WORKDIR /app

COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

COPY app/ ./app/

RUN mkdir -p /app/data

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
