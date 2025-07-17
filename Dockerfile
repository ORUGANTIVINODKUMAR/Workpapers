# 1. Pick a base image
FROM python:3.13-slim

# 2. Install system packages: tesseract + nodejs/npm
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      tesseract-ocr \
      libtesseract-dev \
      nodejs \
      npm \
 && rm -rf /var/lib/apt/lists/*

# 3. Set working dir
WORKDIR /opt/render/project/src

# 4. Copy package.json first and install node deps (cache layer)
COPY package.json package-lock.json ./
RUN npm install

# 5. Copy the rest of your code
COPY . .

# 6. Make sure the uploads/ and merged/ dirs exist
RUN mkdir -p uploads merged

# 7. Create & populate a venv
RUN python -m venv .venv \
 && .venv/bin/pip install --upgrade pip \
 && .venv/bin/pip install \
      "PyPDF2>=3.0.0" \
      "pdfminer.six>=20201018" \
      "pytesseract>=0.3.10" \
      "pdf2image>=1.16.0" \
      "PyMuPDF>=1.20.0" \
      "pdfplumber>=0.8.0" \
      "Pillow>=8.0.0"
# 8. Startup: run Python then Node in one shell
CMD ["sh", "-c", \
    ".venv/bin/python merge_with_bookmarks.py uploads merged/output.pdf && node server.js"]
