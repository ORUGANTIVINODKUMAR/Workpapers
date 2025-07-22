# Base image with Node
FROM node:22-slim

# Environment
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    VENV_PATH=/venv \
    PATH="/venv/bin:$PATH" \
    PORT=3000

# System deps: Python + Tesseract (+ libs PyMuPDF/Pillow need)
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip python3-venv \
    tesseract-ocr tesseract-ocr-eng libtesseract-dev libleptonica-dev \
    libglib2.0-0 libjpeg62-turbo libpng16-16 libopenjp2-7 zlib1g \
    poppler-utils libgl1 ghostscript fonts-dejavu \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*


WORKDIR /app

# Copy manifests first for better layer caching
COPY requirements.txt package.json package-lock.json ./

# Python & Node deps (inside venv → avoids PEP 668 issues)
RUN python3 -m venv $VENV_PATH \
 && $VENV_PATH/bin/pip install --upgrade pip \
 && $VENV_PATH/bin/pip install --no-cache-dir -r requirements.txt \
 && npm ci --omit=dev

# App source
COPY . .

# Create upload dirs at build or runtime (safer at runtime)
RUN mkdir -p /app/uploads /app/merged

# Optional: show binaries
# RUN which tesseract && echo "Tesseract OK"

# Start: run merge once (ignore failure if no files), then start Node
CMD bash -c 'mkdir -p uploads merged; \
             python3 merge_with_bookmarks.py uploads merged/output.pdf || true; \
             node server.js'
