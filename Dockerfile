# 1. Base image with Node.js already installed
FROM node:22.17.0-slim

# 2. Install OS-level dependencies:
#    - Python 3 + venv + pip
#    - Tesseract OCR + dev headers
#    - Poppler utils for PDF/image work
#    - Ghostscript (optional, useful for advanced PDF ops)
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      python3 \
      python3-pip \
      python3-venv \
      tesseract-ocr \
      libtesseract-dev \
      libleptonica-dev \
      tesseract-ocr-eng \
      poppler-utils \
      ghostscript \
      libpoppler-cpp-dev \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*

# 3. Set working directory
WORKDIR /app

# 4. Copy dependency manifests
COPY requirements.txt package.json package-lock.json ./

# 5. Create a Python virtualenv, install Python packages & Node packages
RUN python3 -m venv /venv \
 && /venv/bin/pip install --upgrade pip \
 && /venv/bin/pip install --no-cache-dir -r requirements.txt \
 && npm ci

# 6. Ensure the virtualenv’s bin dir is first in PATH
ENV PATH="/venv/bin:$PATH"

# 7. Copy the rest of your application code
COPY . .

# 8. Expose your port (optional; Docker Hub conventions)
ENV PORT=${PORT:-3000}
EXPOSE $PORT

# 9. At runtime:
#    - Verify Tesseract & Poppler installed
#    - Create uploads/merged dirs
#    - Run your merge script
#    - Start your Node server
CMD which tesseract pdftoppm \
 && mkdir -p uploads merged \
 && python3 merge_with_bookmarks.py uploads merged/output.pdf \
 && node server.js
