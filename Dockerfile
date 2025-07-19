# 1. Base image
FROM python:3.13-slim

# 2. Install OS-level dependencies (Tesseract, Poppler, Node.js/npm)
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

# 4. Copy and install Node.js dependencies
COPY package.json package-lock.json ./
RUN npm install

# 5. Copy and install Python dependencies (suppress root-user warning)
COPY requirements.txt ./
RUN pip install --upgrade pip \
    && pip install --root-user-action=ignore -r requirements.txt

# 6. Copy the rest of your application code
COPY . .

# 7. Ensure upload & merged directories exist
RUN mkdir -p uploads merged

# 8. Expose the port
EXPOSE 3001

# 9. Start Node.js server (which will invoke Python dynamically at runtime)
CMD ["node", "server.js"]
