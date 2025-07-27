# Use the official Node “slim” image
FROM node:22.17.0-slim

# ---- System deps (python, tesseract, poppler for pdfinfo) ----
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        python3 python3-venv python3-pip \
        tesseract-ocr libtesseract-dev libleptonica-dev tesseract-ocr-eng \
        fontconfig poppler-utils \
    && fc-cache -fv \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# ---- Install deps ----
# Copy only manifest files first to leverage Docker cache
COPY requirements.txt package.json package-lock.json ./
RUN python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir -r requirements.txt \
    && npm ci --omit=dev

# Make venv binaries available
ENV PATH="/opt/venv/bin:${PATH}"

# ---- App code ----
COPY . .

# ---- Runtime config ----
ARG PORT=3000
ENV PORT=$PORT
EXPOSE $PORT

# ---- Launch Node (Python is invoked by your upload route) ----
CMD ["node", "server.js"]
