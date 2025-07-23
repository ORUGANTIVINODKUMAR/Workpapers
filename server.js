// server.js
const express = require("express");
const multer = require("multer");
const cors = require("cors");
const { spawn } = require("child_process");
const fs = require("fs");
const fsp = require("fs/promises");
const path = require("path");

const app = express();
const PORT = process.env.PORT || 3001;

const UPLOAD_DIR = path.join(__dirname, "uploads");
const MERGED_DIR = path.join(__dirname, "merged");

// Ensure dirs exist at startup
[UPLOAD_DIR, MERGED_DIR].forEach((dir) => {
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
    console.log(`Created missing directory: ${dir}`);
  }
});

app.use(cors());
// serve merged files so you can GET /merged/merged_xxx.pdf
app.use("/merged", express.static(MERGED_DIR));

// ---- Multer storage config ----
const storage = multer.diskStorage({
  destination: function (req, file, cb) {
    cb(null, UPLOAD_DIR);
  },
  filename: function (req, file, cb) {
    const safeName = `${Date.now()}-${file.originalname}`;
    cb(null, safeName);
  },
});
const upload = multer({ storage });

// ---- Helper to spawn Python merge ----
function runMerge(inputDir, outputPath) {
  return new Promise((resolve, reject) => {
    const pythonCmd = process.env.PYTHON || "/opt/venv/bin/python";

    const py = spawn(pythonCmd, [
      "merge_with_bookmarks.py",
      inputDir,
      outputPath,
    ]);

    py.stdout.on("data", (data) => {
      console.log(`[PY-OUT] ${data}`.trim());
    });

    py.stderr.on("data", (data) => {
      console.error(`[PY-ERR] ${data}`.trim());
    });

    py.on("close", (code) => {
      if (code === 0) resolve(outputPath);
      else reject(new Error(`merge_with_bookmarks.py exited with code ${code}`));
    });
  });
}

// ---- Route ----
app.post("/merge", upload.array("pdfs"), async (req, res) => {
  try {
    if (!req.files || req.files.length === 0) {
      return res.status(400).send("No PDFs uploaded");
    }

    console.log("Uploaded files:");
    req.files.forEach((f) => console.log(f.path));

    await fsp.mkdir(MERGED_DIR, { recursive: true });
    const outputPath = path.join(
      MERGED_DIR,
      `merged_${Date.now()}.pdf`
    );

    const mergedFile = await runMerge(UPLOAD_DIR, outputPath);

    // Send file to client; keep files unless you want to clean up
    res.download(mergedFile, (err) => {
      if (err) console.error("Download error:", err);
      // optional cleanup:
      // req.files.forEach(f => fs.unlinkSync(f.path));
      // fs.unlinkSync(mergedFile);
    });
  } catch (err) {
    console.error(err);
    res.status(500).send("Failed to merge PDFs with bookmarks");
  }
});

// Simple health check
app.get("/healthz", (_req, res) => res.send("ok"));

app.listen(PORT, () => {
  console.log(`Server is running at http://localhost:${PORT}`);
});
