**README.md**

````markdown
# Workpapers

## Overview

Workpapers is a web service that merges uploaded PDF files with bookmarks and serves them via a Node.js backend. It leverages Python (for PDF merging) and Node.js (for the web server).

## Features

- Upload multiple PDFs via a POST request
- Merge PDFs with bookmarks automatically using Tesseract and Poppler
- Download the merged output

## Prerequisites

- Docker (for containerized deployment)
- Node.js >= 18 (if running locally)
- Python 3.13 (if running locally)
- OS dependencies:
  - Poppler (`poppler-utils`)
  - Tesseract (`tesseract-ocr`)

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/ORUGANTIVINODKUMAR/Workpapers.git
   cd Workpapers
````

2. Copy environment variables:

   ```bash
   cp .env.example .env
   ```
3. (Optional) Install dependencies locally:

   ```bash
   # Python
   python3 -m venv venv && source venv/bin/activate
   pip install --upgrade pip
   pip install -r requirements.txt

   # Node.js
   npm install
   ```

## Usage

### With Docker

1. Build the Docker image:

   ```bash
   docker build -t workpapers .
   ```
2. Run the container:

   ```bash
   docker run --env-file .env -p 3000:3000 workpapers
   ```
3. Access your service at `http://localhost:3000`.

### Without Docker

1. Ensure your `.env` file is configured.
2. Start the merge script and server:

   ```bash
   python merge_with_bookmarks.py uploads merged/output.pdf
   node server.js
   ```

## Environment Variables

See `.env.example` for a full list. Key variables include:

* `PORT`: The port on which the Node.js server listens.
* `POPPLER_PATH`: Path to Poppler utilities if not on `PATH`.
* `TESSERACT_PATH`: Path to the Tesseract binary if not on `PATH`.

## API Endpoints

* `GET /`: Serves a simple status page.
* `POST /merge`: Accepts multiple PDF files under field name `files` (multipart/form-data). Returns the merged PDF.

## License

MIT License

````

**.env.example**

```dotenv
# Port for the Node.js server
PORT=3000

# Path to Poppler utils (if not in PATH)
POPPLER_PATH=/usr/bin

# Path to Tesseract binary (if not in PATH)
TESSERACT_PATH=/usr/bin/tesseract

# (Optional) Upload and output directories
# UPLOAD_DIR=uploads
# MERGED_DIR=merged

# (Optional) Log level: debug, info, warn, error
# LOG_LEVEL=info
````
