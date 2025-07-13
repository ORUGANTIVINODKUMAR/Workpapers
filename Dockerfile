FROM node:22.17.0-slim

# Install system dependencies
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      python3 python3-pip \
      tesseract-ocr libtesseract-dev libleptonica-dev \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . .

# Install dependencies
RUN pip3 install --no-cache-dir -r requirements.txt \
 && npm ci

ENV PORT=${PORT:-3000}

# Entry point: run Python script, then start Node server
CMD mkdir -p uploads merged \
  && python3 merge_with_bookmarks.py uploads merged/output.pdf \
  && node server.js
