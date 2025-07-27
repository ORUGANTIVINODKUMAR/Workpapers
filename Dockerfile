# ---- Builder Stage ----
FROM node:22.17.0-slim AS builder

# Install build‑time deps: Python tooling, Poppler, Ghostscript, Tesseract
RUN apt-get update \
 && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      python3 python3-pip \
      python3 python3-venv python3-pip \
      poppler-utils ghostscript \
      tesseract-ocr libtesseract-dev libleptonica-dev tesseract-ocr-eng \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
# ← Add this line to ensure uploads/ already exists at container start
RUN mkdir -p /app/uploads

# Copy dependency manifests
COPY requirements.txt package.json package-lock.json ./

# Create venv + shim ‘python’ → python3, install Python & Node deps
RUN python3 -m venv /opt/venv \
 && ln -sf /opt/venv/bin/python3 /opt/venv/bin/python \
 && /opt/venv/bin/pip install --no-cache-dir -r requirements.txt \
 && npm ci --omit=dev

# Copy your application code
COPY . .



# ---- Runtime Stage ----
FROM node:22.17.0-slim AS runtime

# Install only the runtime bits of Poppler, Ghostscript, Tesseract
RUN apt-get update \
 && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      poppler-utils \
      ghostscript \
      tesseract-ocr libtesseract-dev libleptonica-dev tesseract-ocr-eng \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy built venv (with python shim) and app code from builder
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /app      /app

# Make venv bins first in PATH & disable Python output buffering
ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1

# Expose port and start Node
ARG PORT=3000
ENV PORT=$PORT
EXPOSE $PORT

CMD ["node", "server.js"]
