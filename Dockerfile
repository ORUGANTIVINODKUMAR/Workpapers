# ---- Builder ----
FROM node:22.17.0-slim AS builder

RUN apt-get update \
 && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      python3 python3-venv python3-pip \
      poppler-utils ghostscript \
      tesseract-ocr libtesseract-dev libleptonica-dev tesseract-ocr-eng \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt package.json package-lock.json ./

# Create a venv *and* a `python` shim,
# then install Python & Node deps
RUN python3 -m venv /opt/venv \
 && ln -s /opt/venv/bin/python3 /opt/venv/bin/python \
 && /opt/venv/bin/pip install --no-cache-dir -r requirements.txt \
 && npm ci --omit=dev

COPY . .

# ---- Runtime ----
FROM node:22.17.0-slim AS runtime

# Poppler, Ghostscript, Tesseract runtimes only
RUN apt-get update \
 && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      poppler-utils \
      ghostscript \
      tesseract-ocr libtesseract-dev libleptonica-dev tesseract-ocr-eng \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Bring in the venv (with its `python` shim) + your app
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /app      /app

ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1

ARG PORT=3000
ENV PORT=$PORT
EXPOSE $PORT

CMD ["node", "server.js"]
