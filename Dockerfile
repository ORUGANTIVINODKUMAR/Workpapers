# 1. Base image
FROM python:3.13-slim

# 2. Install OS-level deps: Tesseract OCR, Poppler (for pdf2image), Node.js/npm
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      tesseract-ocr \
      libtesseract-dev \
      poppler-utils \
      nodejs \
      npm \
 && rm -rf /var/lib/apt/lists/*

# 3. Set workdir
WORKDIR /opt/render/project/src

# 4. Copy and install Node dependencies
COPY package.json package-lock.json ./
RUN npm install

# 5. Copy and install Python dependencies
COPY requirements.txt ./
RUN python -m venv .venv \
 && .venv/bin/pip install --upgrade pip \
 && .venv/bin/pip install -r requirements.txt

# 6. Copy your application code
COPY . .

# 7. Ensure the uploads/ and merged/ dirs exist
RUN mkdir -p uploads merged

# 8. Startup: run Python merge script then Node server in one shell
CMD ["sh", "-c", \
    ".venv/bin/python merge_with_bookmarks.py uploads merged/output.pdf && node server.js"]
