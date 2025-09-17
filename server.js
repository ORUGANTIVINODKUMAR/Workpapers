const express = require('express');
const multer = require('multer');
const cors = require('cors');
const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');
const { v4: uuidv4 } = require('uuid');

const app = express();

// Track progress state for frontend
let mergeProgress = { percent: 0, message: "Idle" };

const PORT = process.env.PORT || 3001;

const BASE_UPLOAD_DIR = path.join(__dirname, 'uploads');
const BASE_MERGED_DIR = path.join(__dirname, 'merged');

// Ensure base dirs exist
[BASE_UPLOAD_DIR, BASE_MERGED_DIR].forEach(dir => {
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
    console.log(`Created missing directory: ${dir}`);
  }
});

app.use(cors());
app.use(express.static('public'));

// Multer storage: create a unique temp folder per request
const storage = multer.diskStorage({
  destination: function (req, file, cb) {
    if (!req.userTempDir) {
      const uniqueId = uuidv4();
      req.userTempDir = path.join(BASE_UPLOAD_DIR, uniqueId);
      fs.mkdirSync(req.userTempDir, { recursive: true });
    }
    cb(null, req.userTempDir);
  },
  filename: function (req, file, cb) {
    const safeName = `${Date.now()}-${file.originalname}`;
    cb(null, safeName);
  }
});

const upload = multer({ storage });

// SSE endpoint for frontend progress updates
app.get('/progress', (req, res) => {
  res.setHeader('Content-Type', 'text/event-stream');
  res.setHeader('Cache-Control', 'no-cache');
  res.setHeader('Connection', 'keep-alive');

  const interval = setInterval(() => {
    res.write(`data: ${JSON.stringify(mergeProgress)}\n\n`);
  }, 1000);

  req.on('close', () => clearInterval(interval));
});

// Merge endpoint
app.post('/merge', upload.array('pdfs'), (req, res) => {
  if (!req.files || req.files.length === 0) {
    return res.status(400).send('No files uploaded');
  }

  const inputDir = req.userTempDir; // unique per request
  const outputPath = path.join(BASE_MERGED_DIR, `merged_${uuidv4()}.pdf`);

  mergeProgress = { percent: 10, message: "Uploading files..." };

  console.log("Uploaded files:");
  req.files.forEach(file => console.log(file.path));

  const pythonPath = 'python3';   // works on Render/Linux
  const python = spawn(pythonPath, ['merge_with_bookmarks.py', inputDir, outputPath]);

  python.stdout.on('data', data => {
    const msg = data.toString().trim();
    console.log(`[PY-OUT] ${msg}`);

    if (msg.includes("Processing")) mergeProgress = { percent: 40, message: "Processing pages..." };
    if (msg.includes("Bookmark")) mergeProgress = { percent: 70, message: "Adding bookmarks..." };
    if (msg.includes("Merged PDF created")) mergeProgress = { percent: 100, message: "Finalizing..." };
  });

  python.stderr.on('data', data => {
    console.error(`[PY-ERR] ${data}`);
  });

  python.on('close', (code) => {
    if (code === 0) {
      mergeProgress = { percent: 100, message: "Done! Ready to download." };
      res.download(outputPath, () => {
        // Cleanup inputDir after sending file
        try {
          fs.rmSync(inputDir, { recursive: true, force: true });
        } catch (e) {
          console.error("Failed cleanup:", e);
        }
      });
    } else {
      mergeProgress = { percent: 100, message: "Failed to merge." };
      res.status(500).send('Failed to merge PDFs with bookmarks');
    }
  });
});

app.listen(PORT, () => {
  console.log(`Server is running at http://localhost:${PORT}`);
});
