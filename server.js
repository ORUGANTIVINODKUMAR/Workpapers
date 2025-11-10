<<<<<<< HEAD
const express = require('express');
const multer = require('multer');
const cors = require('cors');
const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');
const { v4: uuidv4 } = require('uuid');
=======
// =============================
//  Document Merger & OCR Server
//  with Multi-User Login + Persistent Clients + Activity Logging
// =============================

const express = require("express");
const multer = require("multer");
const cors = require("cors");
const { spawn } = require("child_process");
const fs = require("fs");
const path = require("path");
const { v4: uuidv4 } = require("uuid");
const session = require("express-session");
const bodyParser = require("body-parser");
>>>>>>> 9938b47 (updated code)

const app = express();

// Track progress state for frontend
let mergeProgress = { percent: 0, message: "Idle" };

const PORT = process.env.PORT || 3001;

<<<<<<< HEAD
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

=======
// =============================
// Data Files
// =============================
const DATA_DIR = path.join(__dirname, "data");
const USERS_FILE = path.join(DATA_DIR, "users.json");
const CLIENT_FILE = path.join(DATA_DIR, "clients.json");
const ACTIVITY_FILE = path.join(DATA_DIR, "activityLogs.json");

if (!fs.existsSync(DATA_DIR)) fs.mkdirSync(DATA_DIR);
if (!fs.existsSync(USERS_FILE)) fs.writeFileSync(USERS_FILE, "[]", "utf-8");
if (!fs.existsSync(CLIENT_FILE)) fs.writeFileSync(CLIENT_FILE, "[]", "utf-8");
if (!fs.existsSync(ACTIVITY_FILE)) fs.writeFileSync(ACTIVITY_FILE, "[]", "utf-8");

function loadUsers() {
  return JSON.parse(fs.readFileSync(USERS_FILE, "utf-8"));
}
function loadClients() {
  return JSON.parse(fs.readFileSync(CLIENT_FILE, "utf-8"));
}
function saveClients(data) {
  fs.writeFileSync(CLIENT_FILE, JSON.stringify(data, null, 2));
}
function logActivity(username, action, metadata = {}) {
  const logs = JSON.parse(fs.readFileSync(ACTIVITY_FILE, "utf-8"));
  logs.push({ username, action, metadata, timestamp: new Date().toISOString() });
  fs.writeFileSync(ACTIVITY_FILE, JSON.stringify(logs, null, 2));
}

// =============================
// Middleware
// =============================
app.use(cors({ origin: "http://localhost:3001", credentials: true }));
app.use(express.static("public"));
app.use(bodyParser.json());
app.use(
  session({
    secret: "super_secret_key_change_this",
    resave: false,
    saveUninitialized: false,
    cookie: { httpOnly: true, sameSite: "lax", secure: false, maxAge: 2 * 60 * 60 * 1000 },
  })
);

// =============================
// Multi-User Authentication
// =============================
app.post("/login", (req, res) => {
  const { username, password } = req.body;
  const users = loadUsers();
  const user = users.find((u) => u.username === username && u.password === password);

  if (user) {
    req.session.authenticated = true;
    req.session.user = username;
    req.session.tasks = [];
    console.log(`✅ User '${username}' logged in.`);
    logActivity(username, "Logged in");
    return res.json({ success: true, redirect: "/client" });
  }

  res.status(401).json({ error: "Invalid username or password" });
});

app.post("/logout", (req, res) => {
  if (req.session.user) logActivity(req.session.user, "Logged out");
  req.session.destroy(() => res.json({ success: true }));
});

function requireAuth(req, res, next) {
  if (req.session.authenticated && req.session.user) return next();
  if (req.xhr || req.headers.accept?.includes("application/json")) {
    return res.status(401).json({ error: "Session expired. Please log in again." });
  }
  res.redirect("/login.html");
}

// =============================
// Directories
// =============================
const BASE_UPLOAD_DIR = path.join(__dirname, "uploads");
const BASE_TASK_DIR = path.join(__dirname, "task_data");
const BASE_MERGED_DIR = path.join(__dirname, "merged");
[BASE_UPLOAD_DIR, BASE_MERGED_DIR, BASE_TASK_DIR].forEach((dir) => {
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
});
// =============================
// Client Management (Per User)
// =============================
app.get("/client", requireAuth, (req, res) => {
  res.sendFile(path.join(__dirname, "public", "client.html"));
});

// Get clients created by the logged-in user only
app.get("/clients", requireAuth, (req, res) => {
  const username = req.session.user;
  const allClients = loadClients();
  const myClients = allClients.filter(c => c.createdBy === username);
  res.json(myClients);
});

// Create new client and assign to logged-in user
app.post("/client", requireAuth, (req, res) => {
  const { tp_name } = req.body;
  if (!tp_name) return res.status(400).json({ error: "Taxpayer name required." });

  const clients = loadClients();
  const id = `client_${uuidv4().slice(0, 6)}`;
  const username = req.session.user;

  const newClient = {
    id,
    tpName: tp_name,
    createdBy: username,
    tasks: []
  };

  clients.push(newClient);
  saveClients(clients);
  logActivity(username, "Created new client", { clientId: id, tpName: tp_name });

  req.session.currentClient = newClient;
  res.json({ success: true, redirect: `/task.html?client=${id}` });
});

// Select an existing client (must belong to logged-in user)
app.post("/select-client/:id", requireAuth, (req, res) => {
  const id = req.params.id;
  const username = req.session.user;

  const clients = loadClients();
  const client = clients.find(c => c.id === id && c.createdBy === username);

  if (!client) {
    return res.status(403).json({ error: "Access denied or client not found." });
  }

  req.session.currentClient = client;
  logActivity(username, "Selected client", { clientId: id });
  res.json({ success: true, redirect: `/task.html?client=${id}` });
});

// Delete client (only if owner)
app.delete("/client/:id", requireAuth, (req, res) => {
  const id = req.params.id;
  const username = req.session.user;

  let clients = loadClients();
  const before = clients.length;
  clients = clients.filter(c => !(c.id === id && c.createdBy === username));

  saveClients(clients);
  logActivity(username, "Deleted client", { clientId: id });

  res.json({ success: clients.length < before });
});


// =============================
// Task Management per Client
// =============================
app.get("/tasks", requireAuth, (req, res) => {
  if (!req.session.currentClient) return res.status(400).json({ error: "No client selected" });

  const clients = loadClients();
  const client = clients.find((c) => c.id === req.session.currentClient.id);
  if (!client) return res.status(404).json({ error: "Client not found" });

  client.tasks.forEach(task => {
    const mergedPath = path.join(BASE_TASK_DIR, task.id, 'merged_output.pdf');
    task.merged = fs.existsSync(mergedPath); // ✅ Only show Download if file exists
    if (task.merged && task.status !== "completed") {
      task.status = "completed";
    } else if (!task.merged && task.status === "completed") {
      task.status = "new"; // If file was deleted, reset status
    }
  });


  res.json(client.tasks);
});

app.post("/tasks", requireAuth, (req, res) => {
  if (!req.session.currentClient) return res.status(400).json({ error: "No client selected" });

  const { name } = req.body;
  if (!name) return res.status(400).json({ error: "Task name required" });

  const taskId = `task_${uuidv4().slice(0, 6)}`;
  const taskPath = path.join(BASE_TASK_DIR, taskId);
  fs.mkdirSync(path.join(taskPath, "input_pdfs"), { recursive: true });

  const newTask = { id: taskId, name, merged: false, status: "new" };

  const clients = loadClients();
  const index = clients.findIndex((c) => c.id === req.session.currentClient.id);
  if (index === -1) return res.status(404).json({ error: "Client not found" });

  clients[index].tasks.push(newTask);
  saveClients(clients);

  logActivity(req.session.user, "Created new task", { clientId: clients[index].id, taskId });

  res.json(newTask);
});

// =============================
// Delete a Task (per client)
// =============================
app.delete("/tasks/:taskId", requireAuth, (req, res) => {
  const { taskId } = req.params;
  const currentClient = req.session.currentClient;

  if (!currentClient) {
    return res.status(400).json({ error: "No client selected." });
  }

  let clients = loadClients();
  const cIndex = clients.findIndex(c => c.id === currentClient.id);
  if (cIndex === -1) return res.status(404).json({ error: "Client not found." });

  const beforeCount = clients[cIndex].tasks.length;
  clients[cIndex].tasks = clients[cIndex].tasks.filter(t => t.id !== taskId);

  // Save updated clients list
  saveClients(clients);

  // Delete associated task folder (optional but good cleanup)
  const taskFolder = path.join(BASE_TASK_DIR, taskId);
  if (fs.existsSync(taskFolder)) {
    try {
      fs.rmSync(taskFolder, { recursive: true, force: true });
      console.log(`🗑 Deleted folder for task: ${taskId}`);
    } catch (err) {
      console.error(`⚠️ Could not delete folder for ${taskId}: ${err.message}`);
    }
  }

  if (clients[cIndex].tasks.length < beforeCount) {
    console.log(`✅ Task deleted: ${taskId}`);
    return res.json({ success: true });
  } else {
    return res.status(404).json({ error: "Task not found." });
  }
});




// =============================
// Merge Route
// =============================
const storage = multer.diskStorage({
  destination: function (req, file, cb) {
    const taskId = req.body.task_id;
    if (!taskId) return cb(new Error("Missing task_id"));
    const taskPath = path.join(BASE_TASK_DIR, taskId, "input_pdfs");
    fs.mkdirSync(taskPath, { recursive: true });
    cb(null, taskPath);
  },
  filename: function (req, file, cb) {
    cb(null, `${Date.now()}-${file.originalname}`);
  },
});
const upload = multer({ storage });

let mergeProgress = { percent: 0, message: "Idle" };
app.get("/progress", (req, res) => {
  res.setHeader("Content-Type", "text/event-stream");
  res.setHeader("Cache-Control", "no-cache");
  res.setHeader("Connection", "keep-alive");
  const interval = setInterval(() => res.write(`data: ${JSON.stringify(mergeProgress)}\n\n`), 1000);
  req.on("close", () => clearInterval(interval));
});

app.post('/merge', requireAuth, upload.array('pdfs'), async (req, res) => {
  const { task_id } = req.body;
  if (!task_id) return res.status(400).json({ error: 'Missing task_id' });
  if (!req.files || req.files.length === 0)
    return res.status(400).json({ error: 'No files uploaded' });

  const taskPath = path.join(BASE_TASK_DIR, task_id);
  const inputDir = path.join(taskPath, 'input_pdfs');
  const outputPath = path.join(taskPath, 'merged_output.pdf');

  // ✅ Remove any existing merged file (start clean)
  if (fs.existsSync(outputPath)) {
    try {
      fs.unlinkSync(outputPath);
      console.log(`🧹 Removed old merged file for ${task_id}`);
    } catch (err) {
      console.error(`⚠️ Could not delete old merged file: ${err.message}`);
    }
  }

  const tp_ssn = req.session.tp_ssn || '';
  const sp_ssn = req.session.sp_ssn || '';

  // ✅ Mark task as in progress
  let clients = loadClients();
  const currentClient = req.session.currentClient;
  const clientIndex = clients.findIndex(c => c.id === currentClient?.id);
  if (clientIndex !== -1) {
    const tIndex = clients[clientIndex].tasks.findIndex(t => t.id === task_id);
    if (tIndex !== -1) {
      clients[clientIndex].tasks[tIndex].status = "in-progress";
      clients[clientIndex].tasks[tIndex].merged = false;
      saveClients(clients);
    }
  }

  mergeProgress = { percent: 10, message: "Starting merge..." };
  console.log(`🧩 Merging PDFs for task ${task_id}`);

  try {
    const pythonPath = process.platform === "win32" ? "python" : "python3";
    const args = ["merge_with_bookmarks.py", inputDir, outputPath, tp_ssn, sp_ssn];
    const python = spawn(pythonPath, args);

    python.stdout.on("data", data => {
      console.log(`[PYTHON] ${data.toString().trim()}`);
      mergeProgress = { percent: 60, message: data.toString().trim() };
    });

    python.stderr.on("data", data => {
      console.error(`[PYTHON ERR] ${data}`);
    });

    python.on("close", code => {
      if (code === 0) {
        console.log(`✅ Merge completed for ${task_id}`);
        mergeProgress = { percent: 100, message: "Merge complete!" };

        // ✅ Update task status to completed + re-save client
        clients = loadClients();
        const cIndex = clients.findIndex(c => c.id === currentClient?.id);
        if (cIndex !== -1) {
          const tIndex = clients[cIndex].tasks.findIndex(t => t.id === task_id);
          if (tIndex !== -1) {
            clients[cIndex].tasks[tIndex].merged = true;
            clients[cIndex].tasks[tIndex].status = "completed";
            clients[cIndex].tasks[tIndex].date = new Date().toISOString();
            saveClients(clients);
          }
        }

        res.json({ success: true, task_id });
      } else {
        console.error(`❌ Merge failed for ${task_id}`);
        res.status(500).json({ error: "Merge failed" });
      }
    });
  } catch (err) {
    console.error("Merge Error:", err);
    res.status(500).json({ error: "Internal error during merge" });
  }
});


// =============================
// File Download
// =============================
app.get("/download/:taskId", requireAuth, (req, res) => {
  const taskId = req.params.taskId;
  const mergedPath = path.join(BASE_TASK_DIR, taskId, "merged_output.pdf");
  if (!fs.existsSync(mergedPath)) return res.status(404).send("Merged file not found.");
  res.download(mergedPath, `${taskId}_merged.pdf`);
});

// =============================
// Admin Activity View (optional)
// =============================
app.get("/activity-logs", requireAuth, (req, res) => {
  const logs = JSON.parse(fs.readFileSync(ACTIVITY_FILE, "utf-8"));
  res.json(logs);
});

// =============================
// Start Server
// =============================
>>>>>>> 9938b47 (updated code)
app.listen(PORT, () => {
  console.log(`🚀 Server running at http://localhost:${PORT}`);
});
