FROM node:22.17.0-slim
 
# Install system dependencies including Tesseract and English language data
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        python3 python3-pip \
        tesseract-ocr libtesseract-dev libleptonica-dev \
        tesseract-ocr-eng \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*
 
WORKDIR /app
 
# Copy only dependency manifests first to leverage Docker cache
COPY requirements.txt package.json package-lock.json ./
 
# Install Python and Node dependencies
RUN pip3 install --no-cache-dir -r requirements.txt \
    && npm ci
 
# Copy the rest of the application code
COPY . .
 
# Expose port and set environment variable
ENV PORT=${PORT:-3000}
 
# Verify tesseract is installed, run OCR script, then start Node server
CMD which tesseract \
    && mkdir -p uploads merged \
&& python3 merge_with_bookmarks.py uploads merged/output.pdf \
    && node server.js
