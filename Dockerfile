# ┌── Stage 1: Python builder
FROM python:3.11-slim AS python-builder

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      poppler-utils \
      tesseract-ocr libtesseract-dev libleptonica-dev tesseract-ocr-eng \
 && rm -rf /var/lib/apt/lists/*

# create virtualenv & install your Python requirements
ENV VENV_PATH=/opt/venv
RUN python3 -m venv $VENV_PATH
COPY requirements.txt .
RUN $VENV_PATH/bin/pip install --no-cache-dir -r requirements.txt


# ┌── Stage 2: Node builder
FROM node:22.17.0-slim AS node-builder
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --omit=dev


# ┌── Stage 3: Final runtime image
FROM node:22.17.0-slim

# install Python runtime + only the OS libs you need at runtime
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      python3 python3-venv python3-pip \
      poppler-utils \
      tesseract-ocr libtesseract-dev libleptonica-dev tesseract-ocr-eng \
 && rm -rf /var/lib/apt/lists/*

ENV PATH="/opt/venv/bin:${PATH}"
WORKDIR /app

# pull in your pre-built venv & node_modules
COPY --from=python-builder /opt/venv /opt/venv
COPY --from=node-builder /app/node_modules ./node_modules

# copy the rest of your app
COPY . .

ARG PORT=3000
ENV PORT=$PORT
EXPOSE $PORT

# only “node server.js” runs at container start—no more installs here!
CMD ["node", "server.js"]
