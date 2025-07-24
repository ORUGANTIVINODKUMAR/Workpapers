 # Stage 3: Final runtime image
 FROM node:22.17.0-slim

# Install Python 3 runtime (so /opt/venv/bin/python works)
 RUN apt-get update \
  && apt-get install -y --no-install-recommends \
      python3 python3-venv python3-pip \
      poppler-utils \
      tesseract-ocr libtesseract-dev libleptonica-dev tesseract-ocr-eng \
  && rm -rf /var/lib/apt/lists/*

 ENV PATH="/opt/venv/bin:${PATH}"

 WORKDIR /app

 # Bring in the pre‑built Python venv
 COPY --from=python-builder /opt/venv /opt/venv

 # Bring in pre‑built node_modules
 COPY --from=node-builder /app/node_modules ./node_modules

 # Copy your application code
 COPY . .

 ARG PORT=3000
 ENV PORT=$PORT
 EXPOSE $PORT

 CMD ["node", "server.js"]
