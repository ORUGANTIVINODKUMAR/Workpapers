# Use an official Node image with Debian slim as a base
FROM node:18-bullseye-slim

# 1. Install Python + OS deps (Poppler & Tesseract)
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      python3 python3-pip \
      poppler-utils \
      tesseract-ocr libtesseract-dev \
 && rm -rf /var/lib/apt/lists/*

# 2. Set workdir
WORKDIR /app

# 3. Install Python deps (cache pip downloads between builds)
COPY requirements.txt .
RUN pip3 install --upgrade pip \
 && pip3 install --no-cache-dir -r requirements.txt

# 4. Install Node deps (cache npm modules between builds)
COPY package.json package-lock.json ./
RUN npm ci --prefer-offline

# 5. Copy the rest of your code
COPY . .

# 6. Ensure upload & merged folders exist
RUN mkdir -p uploads merged

# 7. Expose and health-check
EXPOSE 3001
HEALTHCHECK --interval=30s --timeout=3s CMD curl -f http://localhost:3001/health || exit 1

# 8. Default command: run Python merge, then start Node
CMD ["sh","-c","python3 merge_with_bookmarks.py uploads merged/output.pdf && exec node server.js"]
