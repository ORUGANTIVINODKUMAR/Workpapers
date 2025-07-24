FROM node:22.17.0-slim
 
# ---- System deps (python, tesseract, poppler for pdfinfo) ----
RUN apt-get update \
&& apt-get install -y --no-install-recommends \
    python3 python3-venv python3-pip \
    tesseract-ocr libtesseract-dev libleptonica-dev tesseract-ocr-eng \
&& rm -rf /var/lib/apt/lists/*
 
WORKDIR /app
 
# ---- Install deps ----
COPY requirements.txt package.json package-lock.json ./
RUN python3 -m venv /opt/venv \
&& /opt/venv/bin/pip install --no-cache-dir -r requirements.txt \
&& npm ci --omit=dev
 
# Make venv bins available
ENV PATH="/opt/venv/bin:${PATH}"
 
# ---- App code ----
COPY . .
 
# ---- Runtime config ----
ARG PORT=3000
ENV PORT=$PORT
EXPOSE $PORT
 
# ---- Start only Node. Python is spawned by your upload route ----
CMD ["node", "server.js"]
