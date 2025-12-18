FROM node:22.17.0-slim

# ---- System deps ----
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
    python3 python3-venv python3-pip \
    tesseract-ocr libtesseract-dev libleptonica-dev tesseract-ocr-eng \
    poppler-utils libpoppler-cpp-dev \
    nginx gettext-base \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ---- Install deps ----
COPY requirements.txt package.json package-lock.json ./
RUN python3 -m venv /opt/venv \
 && /opt/venv/bin/pip install --no-cache-dir -r requirements.txt \
 && ( [ -f package-lock.json ] && npm ci --omit=dev || npm install --omit=dev )

ENV PATH="/opt/venv/bin:${PATH}"

# ---- Copy app ----
COPY . .

# ---- Copy nginx template ----
COPY nginx.conf /etc/nginx/nginx.conf.template

ENV PORT=3032
EXPOSE $PORT

# ---- Start nginx + node (Render-safe) ----
CMD envsubst '$PORT' < /etc/nginx/nginx.conf.template > /etc/nginx/nginx.conf \
 && nginx \
 && node server.js
