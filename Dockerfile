FROM node:21-bullseye

# Install system deps
RUN apt-get update && \
    apt-get install -y python3 python3-pip poppler-utils tesseract-ocr && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /srv
COPY package*.json ./
RUN npm install

COPY requirements.txt ./
RUN pip3 install --no-cache-dir -r requirements.txt

COPY . .
EXPOSE 3001
CMD ["npm","start"]
