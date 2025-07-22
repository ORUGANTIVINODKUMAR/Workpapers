FROM node:22.17.0-slim
 
# Install system dependencies including Tesseract and Python
RUN apt-get update \
&& apt-get install -y --no-install-recommends \
        python3 python3-pip python3-venv \
        tesseract-ocr libtesseract-dev libleptonica-dev \
        tesseract-ocr-eng \
&& apt-get clean \
&& rm -rf /var/lib/apt/lists/*
 
WORKDIR /app
 
COPY requirements.txt package.json package-lock.json ./
 
# Use virtualenv for Python dependencies
RUN python3 -m venv /venv \
&& /venv/bin/pip install --no-cache-dir -r requirements.txt \
&& npm ci
 
# Ensure the venv's bin directory is in the path
ENV PATH="/venv/bin:$PATH"
 
COPY . .
 
ENV PORT=${PORT:-3000}
 
CMD which tesseract \
&& mkdir -p uploads merged \
&& python3 merge_with_bookmarks.py uploads merged/output.pdf \
&& node server.js
