const express = require('express');
const multer = require('multer');
const cors = require('cors');
const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');
const { v4: uuidv4 } = require('uuid');  // npm install uuid

const app = express();
const PORT = process.env.PORT || 3001;

const BASE_UPLOAD_DIR = path.join(__dirname, 'uploads');
const BASE_MERGED_DIR = path.join(__dirname, 'merged');

[BASE_UPLOAD_DIR, BASE_MERGED_DIR].forEach(dir => {
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
});

app.use(cors());
app.use(express.static('public'));

// dynamic storage: each request gets its own folder
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

app.post('/merge', upload.array('pdfs'), (req, res) => {
  if (!req.files || req.files.length === 0) {
    return res.status(400).send('No files uploaded');
  }

  const inputDir = req.userTempDir;
  const outputPath = path.join(BASE_MERGED_DIR, `merged_${uuidv4()}.pdf`);

  console.log("Uploaded files for this user:");
  req.files.forEach(file => console.log(file.path));

  const python = spawn('python', ['merge_with_bookmarks.py', inputDir, outputPath]);

  python.stdout.on('data', data => console.log(`[PY-OUT] ${data}`.trim()));
  python.stderr.on('data', data => console.error(`[PY-ERR] ${data}`.trim()));

  python.on('close', (code) => {
    if (code === 0) {
      res.download(outputPath, () => {
        // cleanup user temp dir
        try {
          fs.rmSync(inputDir, { recursive: true, force: true });
        } catch (e) {
          console.error("Failed cleanup:", e);
        }
      });
    } else {
      res.status(500).send('Failed to merge PDFs with bookmarks');
    }
  });
});

app.listen(PORT, () => {
  console.log(`Server running at http://localhost:${PORT}`);
});
