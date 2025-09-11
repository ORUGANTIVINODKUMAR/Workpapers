# ---- Runtime Stage ----
FROM node:22.17.0-slim AS runtime
 
# Install only the runtime bits of Poppler, Ghostscript, Tesseract
RUN apt-get update \
&& DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      python3 python3-pip \
      poppler-utils \
      ghostscript \
      tesseract-ocr libtesseract-dev libleptonica-dev tesseract-ocr-eng \
&& rm -rf /var/lib/apt/lists/*
 
WORKDIR /app
 
# Copy built venv (with python shim) and app code from builder
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /app      /app
 
# Make venv bins first in PATH & disable Python output buffering
ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1
 
# Expose port and start Node
ARG PORT=3000
ENV PORT=$PORT
EXPOSE $PORT
 
CMD ["node", "server.js"]
unusefull
