FROM node:22.17.0-slim

# 1) Install OS + Python + OCR deps
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      python3 python3-pip \
      poppler-utils \
      tesseract-ocr libtesseract-dev libleptonica-dev tesseract-ocr-eng \
 && ln -s /usr/bin/python3 /usr/bin/python \   # ensure "python" is available
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 2) Copy and install Python & Node dependencies
COPY requirements.txt package.json package-lock.json ./
RUN pip3 install --no-cache-dir -r requirements.txt \
 && npm ci --omit=dev

# 3) Copy your app code
COPY . .

# 4) Expose & run
ARG PORT=3000
ENV PORT=$PORT
EXPOSE $PORT
CMD ["node", "server.js"]
