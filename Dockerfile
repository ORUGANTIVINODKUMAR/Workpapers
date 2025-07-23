FROM node:22.17.0-slim

# Install system deps, including venv support
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      python3 python3-venv python3-pip \
      tesseract-ocr libtesseract-dev libleptonica-dev tesseract-ocr-eng \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy manifests
COPY requirements.txt package.json package-lock.json ./

# Create a venv, install Python deps into it, then Node deps
RUN python3 -m venv /opt/venv \
 && . /opt/venv/bin/activate \
 && pip install --no-cache-dir -r requirements.txt \
 && npm ci

# Make the venv’s binaries available to all subsequent steps
ENV PATH="/opt/venv/bin:${PATH}"

# Copy the rest of your code
COPY . .

ENV PORT=${PORT:-3000}

CMD which tesseract \
 && mkdir -p uploads merged \
 && python3 merge_with_bookmarks.py uploads merged/output.pdf \
 && node server.js
