# 1. Base image
FROM python:3.13-slim
 
# 2. Install OS-level deps (Tesseract, Poppler for pdf2image, Node.js/npm)
RUN apt-get update \
&& apt-get install -y --no-install-recommends \
      tesseract-ocr \
      libtesseract-dev \
      poppler-utils \
      nodejs \
      npm \
&& rm -rf /var/lib/apt/lists/*
 
# 3. Set working directory
WORKDIR /opt/render/project/src
 
# 4. Copy only Node dependency manifests, install JS deps
COPY package.json package-lock.json ./
RUN npm install
 
# 5. Copy only Python dependency list, install Python deps
COPY requirements.txt ./
RUN pip install --upgrade pip
RUN pip install -r requirements.txt
# 6. Copy the rest of your application code
COPY . .
 
# 7. Make sure your upload & merged folders exist
RUN mkdir -p uploads merged
 
# 8. At runtime: run your Python merge script, then start your Node server
CMD ["/bin/bash", "-c", "python merge_with_bookmarks.py uploads merged/output.pdf && node server.js"]
