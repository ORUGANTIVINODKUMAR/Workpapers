# syntax=docker/dockerfile:1.4

########## Builder stages ##########

# 1) Python deps
FROM python:3.13-slim AS py-builder
RUN apt-get update \
 && apt-get install -y --no-install-recommends poppler-utils tesseract-ocr libtesseract-dev \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

# 2) Node deps
FROM node:18-alpine AS js-builder
WORKDIR /app
COPY package*.json ./
RUN --mount=type=cache,target=/root/.npm \
    npm ci --prefer-offline

########## Final image ##########

FROM python:3.13-slim
RUN apt-get update \
 && apt-get install -y --no-install-recommends poppler-utils tesseract-ocr libtesseract-dev \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /app

# copy in installed packages
COPY --from=py-builder /usr/local/lib/python3.13/site-packages/ /usr/local/lib/python3.13/site-packages/
COPY --from=js-builder /app/node_modules/ /app/node_modules/

# copy your code
COPY . .

# create upload/merged dirs
RUN mkdir -p uploads merged

# expose your API port
EXPOSE 3001

# health-check
HEALTHCHECK --interval=30s --timeout=5s CMD curl -f http://localhost:3001/health || exit 1

# start script: run merge step on build if possible, then spin up Node
ENTRYPOINT ["sh","-c"]
CMD ["exec node server.js"]
