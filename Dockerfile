FROM python:3.10-slim

# --- System deps required by Playwright browsers AND Tesseract ---
RUN apt-get update && apt-get install -y \
    wget gnupg ca-certificates curl unzip \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libxkbcommon0 \
    libgtk-3-0 libgbm1 libasound2 libxcomposite1 libxdamage1 libxrandr2 \
    libxfixes3 libpango-1.0-0 libcairo2 \
    tesseract-ocr \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# --- Install Playwright + Chromium ---
RUN pip install playwright && playwright install --with-deps chromium

# --- Install uv package manager ---
RUN pip install uv

# Copy your entire repo into /app
WORKDIR /app
COPY . .

ENV PYTHONUNBUFFERED=1
ENV PYTHONIOENCODING=utf-8

# --- Install dependencies using uv ---
# If uv.lock exists, uv sync will install EXACT matching versions
RUN uv sync || (echo "UV FAILED → falling back to pip install" && pip install -r requirements.txt)

# Install gunicorn + uvicorn workers for HuggingFace
RUN pip install gunicorn uvicorn

# HuggingFace runs on port 7860
EXPOSE 7860

# Final command to run FastAPI
CMD ["gunicorn", "http_app:app", "-k", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:7860"]