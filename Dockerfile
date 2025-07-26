# ---- Builder ----
FROM node:22.17.0-slim AS builder

# Install build‑time deps: Python tooling, Poppler, Ghostscript, Tesseract
RUN apt-get update \
 && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      python3 python3-venv python3-pip \
      poppler-utils ghostscript \
      tesseract-ocr libtesseract-dev libleptonica-dev tesseract-ocr-eng \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy manifest files and install Python & Node dependencies
COPY requirements.txt package.json package-lock.json ./
RUN python3 -m venv /opt/venv \
 && /opt/venv/bin/pip install --no-cache-dir -r requirements.txt \
 && npm ci --omit=dev

# Copy your application source
COPY . .



# ---- Runtime ----
FROM node:22.17.0-slim AS runtime

# Only bring in Poppler & Ghostscript runtimes (no dev headers) + Tesseract runtimes
RUN apt-get update \
 && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      poppler-utils \
      ghostscript \
      tesseract-ocr libtesseract-dev libleptonica-dev tesseract-ocr-eng \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy the pre‑built virtualenv and app files from builder
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /app /app

# Expose your venv binaries and disable Python buffering for real‑time logs
ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1

# Runtime port
ARG PORT=3000
ENV PORT=$PORT
EXPOSE $PORT

# Launch only Node; Python gets spawned by your upload/merge route
CMD ["node", "server.js"]
