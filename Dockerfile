FROM node:22.17.0-slim

# 1) Env vars
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    VENV_PATH=/venv \
    PATH="/venv/bin:$PATH" \
    PORT=3000

# 2) System deps
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      python3 python3-pip python3-venv \
      tesseract-ocr tesseract-ocr-eng libtesseract-dev libleptonica-dev \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 3) Copy manifests
COPY requirements.txt package.json package-lock.json ./

# 4) Create venv and install deps
RUN python3 -m venv $VENV_PATH \
 && $VENV_PATH/bin/pip install --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt \
 && npm ci --omit=dev

# 5) Optional: fail fast if PyPDF2 missing
RUN python -c "import PyPDF2; print('PyPDF2 OK')"

# 6) Copy the rest
COPY . .

# 7) Ensure dirs exist (can also do at runtime)
RUN mkdir -p /app/uploads /app/merged

# 8) Start command (shows debug info once)
CMD bash -lc 'which python; python -V; pip list | grep PyPDF2; \
              mkdir -p uploads merged; \
              python merge_with_bookmarks.py uploads merged/output.pdf || true; \
              node server.js'
