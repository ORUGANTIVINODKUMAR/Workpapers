# ---- Builder ----
FROM node:22.17.0-slim AS builder

# Install system deps for build
RUN apt-get update \
 && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      python3 python3-venv python3-pip \
      poppler-utils ghostscript \
      tesseract-ocr libtesseract-dev libleptonica-dev tesseract-ocr-eng \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy manifests, install Python and Node deps
COPY requirements.txt package.json package-lock.json ./
RUN python3 -m venv /opt/venv \
 && /opt/venv/bin/pip install --no-cache-dir -r requirements.txt \
 && npm ci --omit=dev

# Copy app code
COPY . .

# ---- Runtime ----
FROM node:22.17.0-slim AS runtime

# Only bring in the Poppler runtime bits (no build tools)
RUN apt-get update \
 && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      poppler-utils \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy virtualenv and app from builder
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /app /app

# Make venv bins available and unbuffer Python output
ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1

ARG PORT=3000
ENV PORT=$PORT
EXPOSE $PORT

CMD ["node", "server.js"]
