const express = require('express');
const multer = require('multer');
const cors = require('cors');
const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');
 
const app = express();
const PORT = process.env.PORT || 3001;
 
const UPLOAD_DIR = path.join(__dirname, 'uploads');
const MERGED_DIR = path.join(__dirname, 'merged');
 
[UPLOAD_DIR, MERGED_DIR].forEach(dir => {
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
    console.log(`Created missing directory: ${dir}`);
  }
});
 
//const PORT = process.env.PORT || 3001;
app.use(cors());
app.use(express.static('public'));
 
//const upload = multer({ dest: 'uploads/' }); replaced this code with 16 -- 25 code
// To fix the PDF corruption issue,
// Fixed: Storage config with proper filename formatting 
const storage = multer.diskStorage({
  destination: function (req,file, cd){
    cd(null, 'uploads/');
  },
  filename: function (req, file, cd){
    //const originalExt = path.extname(file.originalname) || '.pdf'; // Default to .pdf 
const safeName = `${Date.now()}-${file.originalname}`;
 
    cd(null, safeName);
  }
})
 
const upload = multer({ storage: storage });
 
app.post('/merge', upload.array('pdfs'), (req, res) => {
  const inputDir = 'uploads';
  const outputPath = path.join('merged', `merged_${Date.now()}.pdf`);
 
  //  Log uploaded files (optional, for debugging)
  console.log("Uploaded files:");
  req.files.forEach(file => {
    console.log(file.path);
  });
  const pythonPath = 'C:\\Python312\\python.exe';
  const python = spawn('python', ['merge_with_bookmarks.py', inputDir, outputPath]);
 
  python.stdout.on('data', data => {
    console.log(`[PY-OUT] ${data}`.trim());
  });
  python.stderr.on('data', data => {
    console.error(`[PY-ERR] ${data}`.trim());
  });
 
 
  python.on('close', (code) => {
    if (code === 0) {
      res.download(outputPath, () => {
        // Cleanup
        //fs.readdirSync(inputDir).forEach(file => fs.unlinkSync(path.join(inputDir, file)));
        //fs.unlinkSync(outputPath);
      });
    } else {
      res.status(500).send('Failed to merge PDFs with bookmarks');
    }
  });
}
 
);
 
app.post('/merge', upload.array('pdfs'), (req, res) => {
  console.log("Uploaded files:");
  req.files.forEach(file => {
    console.log(file.path); // This is safe here
  });
 
  // ... rest of your code
});
 
 
app.listen(PORT, () => {
  console.log(`Server is running at http://localhost:${PORT}`);
});
server.js code
