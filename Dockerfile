FROM python:3.11-slim

# Install system dependencies including poppler-utils and tesseract
RUN apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils \
    tesseract-ocr \
    libtesseract-dev \
    libleptonica-dev \
    tesseract-ocr-eng \
    nodejs npm \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy your requirement and package files
COPY requirements.txt package.json package-lock.json ./

# Create and activate Python virtual environment, install Python dependencies and npm packages
RUN python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install --no-cache-dir -r requirements.txt \
    && npm ci --omit=dev

# Add virtual environment binaries to PATH
ENV PATH="/opt/venv/bin:${PATH}"

# Copy the rest of your application code
COPY . .

# Set port (adjust if your app uses a different one)
ARG PORT=3000
ENV PORT=$PORT
EXPOSE $PORT

# Start only node app (adjust command if you want to start Python differently)
CMD ["node", "server.js"]
