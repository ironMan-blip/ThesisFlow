FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
# Longer timeout and more retries so a slow PyPI link does not fail the build
RUN pip install --no-cache-dir --default-timeout=120 --retries 10 -r requirements.txt
COPY . .

CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --proxy-headers --forwarded-allow-ips='*'"]
