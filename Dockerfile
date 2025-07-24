FROM node:22.17.0-slim

# Install OS/Python/OCR deps in one RUN
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      python3 python3-pip \
      poppler-utils \
      tesseract-ocr libtesseract-dev libleptonica-dev tesseract-ocr-eng && \
    ln -s /usr/bin/python3 /usr/bin/python && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy & install deps
COPY requirements.txt package.json package-lock.json ./
RUN pip3 install --no-cache-dir -r requirements.txt && \
    npm ci --omit=dev

COPY . .

ARG PORT=3000
ENV PORT=$PORT
EXPOSE $PORT

CMD ["node", "server.js"]
