const express = require('express');
const multer = require('multer');
const cors = require('cors');
const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');

const app = express();
const PORT = process.env.PORT || 3001;

// Directories for uploads and merged PDFs
const UPLOAD_DIR = path.join(__dirname, 'uploads');
const MERGED_DIR = path.join(__dirname, 'merged');
[UPLOAD_DIR, MERGED_DIR].forEach(dir => {
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
    console.log(`Created missing directory: ${dir}`);
  }
});

app.use(cors());
app.use(express.static('public'));

// ─── Health‑check endpoint ──────────────────────────────────────────────────────
app.get('/health', (req, res) => {
  res.json({ status: 'ok', timestamp: Date.now() });
});

// ─── Multer storage config ───────────────────────────────────────────────────────
const storage = multer.diskStorage({
  destination: (req, file, cd) => cd(null, UPLOAD_DIR),
  filename:    (req, file, cd) => {
    const safeName = `${Date.now()}-${file.originalname}`;
    cd(null, safeName);
  }
});
const upload = multer({ storage });

// ─── Merge route with logging & timing ──────────────────────────────────────────
app.post('/merge', upload.array('pdfs'), (req, res) => {
  console.log(`[/merge] request received at ${new Date().toISOString()}`);
  console.time('[/merge] total');

  const inputDir = UPLOAD_DIR;
  const outputFilename = `merged_${Date.now()}.pdf`;
  const outputPath = path.join(MERGED_DIR, outputFilename);

  // Log each uploaded file path
  req.files.forEach(file => console.log('[UPLOAD]', file.path));

  // Spawn the Python script (python should point to your venv’s interpreter)
  const python = spawn('python', [
    'merge_with_bookmarks.py',
    inputDir,
    outputPath
  ]);

  python.stdout.on('data', data => {
    console.log(`[PY-OUT] ${data}`.trim());
  });
  python.stderr.on('data', data => {
    console.error(`[PY-ERR] ${data}`.trim());
  });

  python.on('close', code => {
    console.timeEnd('[/merge] total');
    if (code === 0) {
      // Send the merged PDF back
      res.download(outputPath, outputFilename, err => {
        if (err) console.error('[DOWNLOAD-ERR]', err);
        // Optionally: cleanup here
      });
    } else {
      res.status(500).send('Failed to merge PDFs with bookmarks');
    }
  });
});

// ─── Server startup ─────────────────────────────────────────────────────────────
app.listen(PORT, () => {
  console.log(`🚀 Server listening on port ${PORT} at ${new Date().toISOString()}`);
});
