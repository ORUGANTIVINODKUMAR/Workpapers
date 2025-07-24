FROM node:22.17.0-slim

# 1) Install Python3, venv support, Poppler & Tesseract
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      python3 python3-pip python3-venv \
      poppler-utils \
      tesseract-ocr libtesseract-dev libleptonica-dev tesseract-ocr-eng && \
    rm -rf /var/lib/apt/lists/*

# 2) Create a virtualenv and upgrade pip/setuptools
ENV VENV_PATH=/opt/venv
RUN python3 -m venv $VENV_PATH && \
    $VENV_PATH/bin/pip install --upgrade pip setuptools wheel

# 3) Ensure the virtualenv’s python/pip are first in PATH
ENV PATH="$VENV_PATH/bin:$PATH"

WORKDIR /app

# 4) Copy dependency manifests
COPY requirements.txt package.json package-lock.json ./

# 5) Install Python deps into venv, then Node deps
RUN pip install --no-cache-dir -r requirements.txt && \
    npm ci --omit=dev

# 6) Copy your application code
COPY . .

ARG PORT=3000
ENV PORT=$PORT
EXPOSE $PORT

# 7) Only Node runs at container start
CMD ["node", "server.js"]
