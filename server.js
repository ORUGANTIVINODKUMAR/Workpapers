const express = require('express');
const multer = require('multer');
const cors = require('cors');
const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');

const app = express();
const PORT = process.env.PORT || 3001;

// ─── Directory setup ───────────────────────────────────────────────
const UPLOAD_DIR = path.join(__dirname, 'uploads');
const MERGED_DIR = path.join(__dirname, 'merged');
[UPLOAD_DIR, MERGED_DIR].forEach(dir => {
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
    console.log(`[INIT] Created missing directory: ${dir}`);
  }
});

app.use(cors());
app.use(express.static('public'));

// ─── Health-check ──────────────────────────────────────────────────
app.get('/health', (req, res) => {
  res.json({ status: 'ok', timestamp: Date.now() });
});

// ─── Multer config ─────────────────────────────────────────────────
const storage = multer.diskStorage({
  destination: (req, file, cb) => cb(null, UPLOAD_DIR),
  filename: (req, file, cb) => {
    const safeName = `${Date.now()}-${file.originalname}`;
    cb(null, safeName);
  }
});
const upload = multer({ storage });

// ─── /merge route with debug-friendly timing ───────────────────────
app.post('/merge', upload.array('pdfs'), (req, res) => {
  const requestId = Date.now();
  const timerLabel = `[/merge] total-${requestId}`;

  console.log(`[/merge] request received at ${new Date().toISOString()}`);
  console.time(timerLabel);

  const inputDir = UPLOAD_DIR;
  const outputFilename = `merged_${requestId}.pdf`;
  const outputPath = path.join(MERGED_DIR, outputFilename);

  req.files.forEach(file => console.log(`[UPLOAD-${requestId}]`, file.path));

  const python = spawn('python', [
    'merge_with_bookmarks.py',
    inputDir,
    outputPath
  ]);

  python.stdout.on('data', data => {
    console.log(`[PY-OUT-${requestId}] ${data}`.trim());
  });

  python.stderr.on('data', data => {
    console.error(`[PY-ERR-${requestId}] ${data}`.trim());
  });

  python.on('close', code => {
    console.timeEnd(timerLabel);
    if (code === 0) {
      res.download(outputPath, outputFilename, err => {
        if (err) {
          console.error(`[DOWNLOAD-ERR-${requestId}]`, err);
        }
        // Optionally handle cleanup if needed
      });
    } else {
      res.status(500).send('Failed to merge PDFs with bookmarks');
    }
  });
});

// ─── Start server ───────────────────────────────────────────────────
app.listen(PORT, () => {
  console.log(`🚀 Server listening on port ${PORT} at ${new Date().toISOString()}`);
});
