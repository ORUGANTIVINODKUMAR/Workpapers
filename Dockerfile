FROM python:3.13-slim

# ← this is your “Pre-Deploy” hook, but baked into the image:
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
       tesseract-ocr \
       libtesseract-dev \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/render/project/src
COPY . .

# ← this replaces “Build Command”:
RUN python -m venv .venv \
 && .venv/bin/pip install --upgrade pip \
 && .venv/bin/pip install -r requirements.txt

# ← this replaces “Start Command”:
CMD [".venv/bin/python", "merge_with_bookmarks.py", "uploads", "merged/output.pdf", "&&", "node", "server.js"]
