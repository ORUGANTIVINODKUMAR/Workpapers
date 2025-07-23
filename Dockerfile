FROM node:22.17.0-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
    python3 python3-venv python3-pip \
    tesseract-ocr libtesseract-dev libleptonica-dev tesseract-ocr-eng \
    poppler-utils \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt package.json package-lock.json ./

RUN python3 -m venv /opt/venv \
 && . /opt/venv/bin/activate \
 && pip install --no-cache-dir -r requirements.txt \
 && npm ci

ENV PATH="/opt/venv/bin:${PATH}"
COPY . .

ENV PORT=${PORT:-3000}

CMD which tesseract \
 && pdfinfo -v \
 && mkdir -p uploads merged \
 && python3 merge_with_bookmarks.py uploads merged/output.pdf \
 && node server.js
