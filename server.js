const express = require('express');
const multer = require('multer');
const cors = require('cors');
const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');

const app = express();
const PORT = process.env.PORT || 3001;

// Absolute paths for uploads and merged output
const UPLOAD_DIR = path.join(__dirname, 'uploads');
const MERGED_DIR = path.join(__dirname, 'merged');

// Ensure those directories exist at startup
[UPLOAD_DIR, MERGED_DIR].forEach(dir => {
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
    console.log(`Created missing directory: ${dir}`);
  }
});

app.use(cors());
app.use(express.static('public'));

// Multer storage configuration
const storage = multer.diskStorage({
  destination: (req, file, cb) => cb(null, UPLOAD_DIR),
  filename:    (req, file, cb) => cb(null, `${Date.now()}-${file.originalname}`)
});
const upload = multer({ storage });

// Single merge endpoint
app.post('/merge', upload.array('pdfs'), (req, res) => {
  const inputDir  = UPLOAD_DIR;
  const outputPath = path.join(MERGED_DIR, `merged_${Date.now()}.pdf`);

  console.log('Uploaded files:');
  req.files.forEach(f => console.log(`  ${f.path}`));

  // Use the Python interpreter from our venv
  const pythonBin = '/opt/venv/bin/python';
  const scriptPath = path.join(__dirname, 'merge_with_bookmarks.py');

  const python = spawn(pythonBin, [scriptPath, inputDir, outputPath]);
  console.log('Spawning merge process…');
  const proc = spawn('python3', ['merge_with_bookmarks.py', filePath], {
    env: process.env,
  });
  proc.stdout.on('data', data => {
    console.log(`[merge stdout] ${data}`);
  });

  proc.stderr.on('data', data => {
    console.error(`[merge stderr] ${data}`);
  });

  proc.on('error', err => {
    console.error('Merge process error:', err);
  });

  proc.on('exit', (code, signal) => {
    console.log(`Merge process exited with code ${code}, signal ${signal}`);
  });
  python.stdout.on('data', data => {
    console.log(`[PY-OUT] ${data}`.trim());
  });
  python.stderr.on('data', data => {
    console.error(`[PY-ERR] ${data}`.trim());
  });
  
  python.on('close', code => {
    if (code === 0) {
      res.download(outputPath, err => {
        if (err) {
          console.error('Download error:', err);
          res.sendStatus(500);
        }
        // (Optional cleanup could go here)
      });
    } else {
      res.status(500).send('Failed to merge PDFs with bookmarks');
    }
  });
});

app.listen(PORT, () => {
  console.log(`Server is running at http://localhost:${PORT}`);
});
