FROM node:22.17.0-slim

# ---- Install system dependencies ----
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
    python3 python3-venv python3-pip \
    poppler-utils ghostscript \
    tesseract-ocr libtesseract-dev libleptonica-dev tesseract-ocr-eng \
 && rm -rf /var/lib/apt/lists/*

# ---- Set environment variables for debugging and reliability ----
ENV PYTHONUNBUFFERED=1
ENV VENV_PATH=/opt/venv
ENV PATH="$VENV_PATH/bin:$PATH"

WORKDIR /app

# ---- Copy application source code BEFORE installing dependencies ----
COPY . .

# ---- Create virtual environment and install dependencies ----
RUN python3 -m venv $VENV_PATH \
 && $VENV_PATH/bin/pip install --no-cache-dir --upgrade pip setuptools wheel \
 && pip install --no-cache-dir -r requirements.txt \
 && npm ci --omit=dev

# ---- Expose your app port ----
ARG PORT=3000
ENV PORT=$PORT
EXPOSE $PORT

# ---- Start the Node.js server ----
CMD ["node", "server.js"]
