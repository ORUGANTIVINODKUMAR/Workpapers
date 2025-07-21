# 1. Base Python image
FROM python:3.11-slim

# 2. Install Tesseract, Poppler, Node.js, and system tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    poppler-utils \
    nodejs \
    npm \
    curl \
 && rm -rf /var/lib/apt/lists/*

# 3. Set working directory
WORKDIR /opt/render/project/src

# 4. Copy dependency files and install
COPY package.json package-lock.json ./
RUN npm install

COPY requirements.txt ./
RUN pip install --upgrade pip && pip install --root-user-action=ignore -r requirements.txt

# 5. Copy source code
COPY . .

# 6. Make upload dirs
RUN mkdir -p uploads merged

# 7. Expose your desired port
EXPOSE 3001

# 8. Run your app
CMD ["node", "server.js"]
