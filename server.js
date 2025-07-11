// server.js
const express   = require('express');
const multer    = require('multer');
const cors      = require('cors');
const { spawn } = require('child_process');
const fs        = require('fs');
const path      = require('path');

const app  = express();
const PORT = process.env.PORT || 3001;

// ── CONSTANTS ───────────────────────────────────────
const ROOT_DIR    = __dirname;
const UPLOAD_DIR  = path.join(ROOT_DIR, 'uploads');
const MERGE_DIR   = path.join(ROOT_DIR, 'merged');
const PYTHON_CMD  = 'python3';  // on Render use 'python3'
const SCRIPT_PATH = path.join(ROOT_DIR, 'merge_with_bookmarks.py');

// ── ENSURE DIRECTORIES EXIST ───────────────────────
[ UPLOAD_DIR, MERGE_DIR ].forEach(dir => {
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
});

// ── MIDDLEWARE ─────────────────────────────────────
app.use(cors());
app.use(express.static('public'));  // serve static assets if any

// ── MULTER SETUP ────────────────────────────────────
const storage = multer.diskStorage({
  destination: (req, file, cb) => { cb(null, UPLOAD_DIR); },
  filename:    (req, file, cb) => {
    const safeName = `${Date.now()}-${file.originalname}`;
    cb(null, safeName);
  }
});
const upload = multer({ storage });

// ── MERGE ENDPOINT ─────────────────────────────────
app.post('/merge', upload.array('pdfs'), (req, res) => {
  console.log('Uploaded files:', req.files.map(f => f.path));

  // build output path
  const outName    = `merged_${Date.now()}.pdf`;
  const outputPath = path.join(MERGE_DIR, outName);

  // spawn Python merger
  const py = spawn(
    PYTHON_CMD,
    [ SCRIPT_PATH, UPLOAD_DIR, outputPath ],
    { cwd: ROOT_DIR, env: process.env }
  );

  py.stdout.on('data', data => {
    console.log(`[PY-OUT] ${data}`.trim());
  });
  py.stderr.on('data', data => {
    console.error(`[PY-ERR] ${data}`.trim());
  });

  py.on('close', code => {
    if (code === 0) {
      // success → send file
      res.download(outputPath, outName, err => {
        if (err) {
          console.error('Download error:', err);
          res.sendStatus(500);
        } else {
          // optional: clean up both uploads and merged
          fs.readdirSync(UPLOAD_DIR).forEach(f => fs.unlinkSync(path.join(UPLOAD_DIR, f)));
          fs.unlinkSync(outputPath);
        }
      });
    } else {
      console.error(`merge script exited with code ${code}`);
      res.status(500).send('Failed to merge PDFs with bookmarks');
    }
  });
});

// ── START SERVER ───────────────────────────────────
app.listen(PORT, () => {
  console.log(`Server running at http://localhost:${PORT}`);
});
