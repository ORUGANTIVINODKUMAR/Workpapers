const express = require('express');
const multer = require('multer');
const cors = require('cors');
const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');

const app = express();
const PORT = process.env.PORT || 3001;
const PYTHON = process.env.PYTHON_PATH || 'python3';

const UPLOAD_DIR = path.join(__dirname, 'uploads');
const MERGED_DIR = path.join(__dirname, 'merged');

// Ensure upload & merged dirs exist
[UPLOAD_DIR, MERGED_DIR].forEach(dir => {
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
    console.log(`Created missing directory: ${dir}`);
  }
});

app.use(cors());
app.use(express.static('public'));

// Health check endpoint
app.get('/health', (req, res) => {
  res.sendStatus(200);
});

// Configure Multer storage to preserve file extensions and avoid collisions
const storage = multer.diskStorage({
  destination: (_, __, cb) => cb(null, UPLOAD_DIR),
  filename: (_, file, cb) => {
    const timestamp = Date.now();
    const safeName = `${timestamp}-${file.originalname}`;
    cb(null, safeName);
  }
});
const upload = multer({ storage });

// Merge endpoint
app.post('/merge', upload.array('pdfs'), (req, res) => {
  console.log('Uploaded files:');
  req.files.forEach(file => console.log(file.path));

  const outputFileName = `merged_${Date.now()}.pdf`;
  const outputPath = path.join(MERGED_DIR, outputFileName);

  // Spawn Python merge script
  const python = spawn(PYTHON, ['merge_with_bookmarks.py', UPLOAD_DIR, outputPath], {
    stdio: 'inherit'
  });

  python.on('close', code => {
    if (code === 0) {
      res.download(outputPath, outputFileName, err => {
        if (err) console.error('Download error:', err);
        // Optionally clean up files here
      });
    } else {
      console.error(`Python script exited with code ${code}`);
      res.status(500).send('Failed to merge PDFs with bookmarks');
    }
  });
});

// Start server and handle graceful shutdown
const server = app.listen(PORT, () => {
  console.log(`Server is running at http://localhost:${PORT}`);
});

process.on('SIGTERM', () => {
  console.log('SIGTERM received, shutting down gracefully');
  server.close(() => {
    console.log('Closed out remaining connections');
    process.exit(0);
  });
  // Force shutdown after 10 seconds
  setTimeout(() => process.exit(1), 10_000);
});
