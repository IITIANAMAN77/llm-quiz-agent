FROM python:3.10-slim

RUN apt-get update && apt-get install -y \
    wget gnupg ca-certificates curl unzip \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libxkbcommon0 \
    libgtk-3-0 libgbm1 libasound2 libxcomposite1 libxdamage1 libxrandr2 \
    libxfixes3 libpango-1.0-0 libcairo2 \
    tesseract-ocr ffmpeg \
    && rm -rf /var/lib/apt/lists/*

RUN pip install playwright && playwright install --with-deps chromium

RUN pip install uv

WORKDIR /app
COPY . .

ENV PYTHONUNBUFFERED=1
ENV PYTHONIOENCODING=utf-8

RUN uv sync || pip install -r requirements.txt || true

RUN pip install gunicorn uvicorn

EXPOSE 7860

CMD ["gunicorn", "http_app:app", "-k", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:7860"]