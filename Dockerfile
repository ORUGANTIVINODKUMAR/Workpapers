FROM node:21-bullseye

# 1) Install Ubuntu packages, including the Tesseract engine
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      python3 python3-pip poppler-utils tesseract-ocr \
 && rm -rf /var/lib/apt/lists/*

# 2) Node setup
WORKDIR /srv
COPY package*.json ./
RUN npm install

# 3) Python setup
COPY requirements.txt ./
RUN pip3 install --no-cache-dir -r requirements.txt

# 4) Copy your code & expose the port
COPY . .
EXPOSE 3001

# 5) Launch
CMD ["npm","start"]
