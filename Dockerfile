FROM python:3.13-slim

# Install Tesseract system binary
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      tesseract-ocr \
      libtesseract-dev \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/render/project/src
COPY . .

# Install Python deps
RUN python -m venv .venv \
 && .venv/bin/pip install -r requirements.txt

# If you have any Node steps, install them here too:
# RUN npm install

CMD [".venv/bin/python", "merge_with_bookmarks.py"]
