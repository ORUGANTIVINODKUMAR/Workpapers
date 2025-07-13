# Use the official Node image (matches your package.json engine)
FROM node:21.2.0-bullseye

# Install Python, pip, and Poppler (for pdf2image)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       python3 python3-pip poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /srv

# Install Node dependencies
COPY package*.json ./
RUN npm install

# Install Python dependencies
COPY requirements.txt ./
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy the rest of your code
COPY . .

# Expose the same port your Express server uses
EXPOSE 3001

# Launch via package.json “start” script
CMD ["npm", "start"]
