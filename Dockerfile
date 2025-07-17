# 1. Base image
FROM python:3.13-slim

# 2. Install OS-level deps: Tesseract OCR + Node.js/npm
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      tesseract-ocr \
      libtesseract-dev \
      nodejs \
      npm \
 && rm -rf /var/lib/apt/lists/*

# 3. Set working directory
WORKDIR /opt/render/project/src

# 4. Copy package.json for Node dependencies (cache layer)
COPY package.json package-lock.json ./
RUN npm install

# 5. Create and activate virtualenv, then install Python deps inline
RUN python -m venv .venv \
 && .venv/bin/pip install --upgrade pip \
 && .venv/bin/pip install -r so.txt \
 && .venv/bin/pip install PyPDF2
# 6. Copy the rest of your code
COPY . .

# 7. Ensure upload/merged dirs exist
RUN mkdir -p uploads merged

# 8. Startup: run Python merge script then Node server in one shell
CMD ["sh", "-c", \
    ".venv/bin/python merge_with_bookmarks.py uploads merged/output.pdf && node server.js"]
