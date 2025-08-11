# 1) Base image with Python
FROM python:3.13-slim
 
# 2) Install Tesseract + its libs so pytesseract can call it
RUN apt-get update \
&& apt-get install -y --no-install-recommends \
      tesseract-ocr \
      libtesseract-dev \
      libleptonica-dev \
&& rm -rf /var/lib/apt/lists/*
 
# 3) Copy your source code in
WORKDIR /app
COPY . .
 
# 4) Install Python & Node dependencies
RUN pip install --no-cache-dir -r requirements.txt \
&& npm install
 
# 5) Expose the port and define the startup
ENV PORT=${PORT:-3000}
CMD mkdir -p uploads merged \
&& python merge_with_bookmarks.py uploads merged/output.pdf \
    && node server.js
