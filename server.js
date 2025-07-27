// server.js
const express = require("express");
const multer  = require("multer");
const { spawn } = require("child_process");
const path    = require("path");
const fs      = require("fs");

// ── Configure multer to write uploads into /app/uploads
const UPLOAD_DIR = path.join(__dirname, "uploads");
fs.mkdirSync(UPLOAD_DIR, { recursive: true });
const upload = multer({ dest: UPLOAD_DIR });

const app = express();
const PORT = process.env.PORT || 3000;

// ── Upload endpoint
// Expects a field named "pdf"
app.post("/upload", upload.single("pdf"), (req, res) => {
  if (!req.file) {
    console.error("[upload] No file received");
    return res.status(400).json({ error: "No file uploaded" });
  }

  const filePath = req.file.path;
  console.log("[upload] Received file at", filePath);
  console.log("[upload] Spawning merge process…");

  // Spawn the Python script with the uploaded path and an output path
  const outputPath = path.join(UPLOAD_DIR, `merged-${Date.now()}.pdf`);
  const proc = spawn("python3", [
    "merge_with_bookmarks.py",
    filePath,
    outputPath
  ], {
    env: process.env
  });

  // Log any stdout from the Python script
  proc.stdout.on("data", data => {
    for (let line of data.toString().split("\n")) {
      if (line.trim()) console.log("[merge stdout]", line);
    }
  });

  // Log any stderr from the Python script
  proc.stderr.on("data", data => {
    for (let line of data.toString().split("\n")) {
      if (line.trim()) console.error("[merge stderr]", line);
    }
  });

  // Handle script exit
  proc.on("exit", (code, signal) => {
    console.log(`[merge exit] code=${code} signal=${signal}`);
    if (code === 0) {
      // Success → send back the merged file path (or URL if you serve it)
      res.json({
        success: true,
        mergedFile: `/downloads/${path.basename(outputPath)}`
      });
    } else {
      res.status(500).json({
        error: `Merge process exited with code ${code}`
      });
    }
  });

  // Handle spawn errors
  proc.on("error", err => {
    console.error("[merge error]", err);
    res.status(500).json({ error: err.message });
  });
});

// ── (Optional) Serve the merged files
app.use("/downloads", express.static(UPLOAD_DIR));

app.listen(PORT, () => {
  console.log(`Server listening on port ${PORT}`);
});
