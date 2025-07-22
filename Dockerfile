FROM node:22.17.0-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_NO_CACHE_DIR=1 \
    PYTHONUNBUFFERED=1

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip python3-dev \
    build-essential gcc g++ make pkg-config \
    tesseract-ocr libtesseract-dev libleptonica-dev tesseract-ocr-eng \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy dependency manifests first
COPY requirements.txt ./
RUN pip3 install -r requirements.txt

COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

# Now the rest of the source
COPY . .

ENV PORT=${PORT:-3000}

CMD set -eux; \
    which tesseract; \
    mkdir -p uploads merged; \
    python3 merge_with_bookmarks.py uploads merged/output.pdf; \
    node server.js
