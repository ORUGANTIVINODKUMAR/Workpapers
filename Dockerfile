FROM node:22.17.0-slim

# System deps (add python3-venv!) + Tesseract
RUN apt-get update \
  && apt-get install -y --no-install-recommends \
       python3 python3-venv python3-pip \
       tesseract-ocr libtesseract-dev libleptonica-dev tesseract-ocr-eng \
       build-essential \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# --- Python deps in a virtualenv ---
ENV VIRTUAL_ENV=/opt/venv
RUN python3 -m venv "$VIRTUAL_ENV"
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

COPY requirements.txt ./
RUN pip install --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

# --- Node deps (separate layer for caching) ---
COPY package.json package-lock.json ./
RUN npm ci

# App source
COPY . .

# Port (set a default properly)
ENV PORT=3000

# Start
# if merge_with_bookmarks.py must run at container start, keep it; otherwise move it to build or your app logic
CMD bash -lc 'which tesseract && mkdir -p uploads merged && \
              python3 merge_with_bookmarks.py uploads merged/output.pdf && \
              node server.js'
