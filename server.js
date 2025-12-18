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

const app = express();

// Track progress state for frontend
let mergeProgress = { percent: 0, message: "Idle" };
const PORT = process.env.PORT || 3032;

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
app.use(bodyParser.json({ limit: '110mb' }));
app.use(bodyParser.urlencoded({ limit: '110mb', extended: true }));
app.use(
  session({
    secret: "super_secret_key_change_this",
    resave: false,
    saveUninitialized: false,
    cookie: {
      httpOnly: true,
      sameSite: "lax",
      secure: false,
      maxAge: 2 * 60 * 60 * 1000, // 2 hours
    },
  })
);

// =============================
// Root Redirect
// =============================
app.get("/", (req, res) => {
  if (req.session?.authenticated && req.session?.user) {
    res.redirect("/client");
  } else {
    res.redirect("/login.html");
  }
});

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

app.get("/clients", requireAuth, (req, res) => {
  const username = req.session.user;
  const allClients = loadClients();
  const myClients = allClients.filter((c) => c.createdBy === username);
  res.json(myClients);
});

app.post("/client", requireAuth, (req, res) => {
  const { tp_name, sp_name, tp_ssn, sp_ssn } = req.body;

  if (!tp_name || !tp_ssn) {
    return res.status(400).json({ error: "Taxpayer name & SSN required." });
  }

  const clients = loadClients();
  const id = `client_${uuidv4().slice(0, 6)}`;
  const username = req.session.user;

  const newClient = {
    id,
    tpName: tp_name,
    tpSSN: tp_ssn,
    spName: sp_name || "",
    spSSN: sp_ssn || "",
    createdBy: username,
    tasks: []
  };

  clients.push(newClient);
  saveClients(clients);

  req.session.currentClient = newClient;

  res.json({ success: true, redirect: `/task.html?client=${id}` });
});

app.post("/select-client/:id", requireAuth, (req, res) => {
  const id = req.params.id;
  const username = req.session.user;

  const clients = loadClients();
  const client = clients.find((c) => c.id === id && c.createdBy === username);

  if (!client) {
    return res.status(403).json({ error: "Access denied or client not found." });
  }

  req.session.currentClient = client;
  res.json({ success: true, redirect: `/task.html?client=${id}` });
});

app.delete("/client/:id", requireAuth, (req, res) => {
  const id = req.params.id;
  const username = req.session.user;

  let clients = loadClients();
  const before = clients.length;
  clients = clients.filter((c) => !(c.id === id && c.createdBy === username));

  saveClients(clients);

  res.json({ success: clients.length < before });
});

// =============================
// Task Management
// =============================
app.get("/tasks", requireAuth, (req, res) => {
  if (!req.session.currentClient)
    return res.status(400).json({ error: "No client selected" });

  const clients = loadClients();
  const client = clients.find((c) => c.id === req.session.currentClient.id);
  if (!client) return res.status(404).json({ error: "Client not found" });


  // -------------------------
  //   FIXED STATUS LOGIC
  // -------------------------
  client.tasks.forEach((task) => {
    const mergedPath = path.join(BASE_TASK_DIR, task.id, "merged_output.pdf");
    task.merged = fs.existsSync(mergedPath);

    if (task.merged) {
      task.status = "completed";
    }
    else if (task.status === "in-progress") {
      task.status = "in-progress";
    }
    else if (task.status === "failed") {
      task.status = "failed";
    }
    else {
      task.status = "new";
    }
  });


  res.json(client.tasks);
});


app.post("/tasks", requireAuth, (req, res) => {
  if (!req.session.currentClient)
    return res.status(400).json({ error: "No client selected" });

  const { name } = req.body;
  if (!name) return res.status(400).json({ error: "Task name required" });

  const taskId = `task_${uuidv4().slice(0, 6)}`;
  const taskPath = path.join(BASE_TASK_DIR, taskId);
  fs.mkdirSync(path.join(taskPath, "input_pdfs"), { recursive: true });

  const newTask = { id: taskId, name, merged: false, status: "new" };

  const clients = loadClients();
  const index = clients.findIndex((c) => c.id === req.session.currentClient.id);
  clients[index].tasks.push(newTask);

  saveClients(clients);

  res.json(newTask);
});

app.delete("/tasks/:taskId", requireAuth, (req, res) => {
  const { taskId } = req.params;
  const currentClient = req.session.currentClient;

  let clients = loadClients();
  const cIndex = clients.findIndex((c) => c.id === currentClient.id);

  const beforeCount = clients[cIndex].tasks.length;
  clients[cIndex].tasks = clients[cIndex].tasks.filter((t) => t.id !== taskId);

  saveClients(clients);

  const taskFolder = path.join(BASE_TASK_DIR, taskId);
  if (fs.existsSync(taskFolder)) {
    fs.rmSync(taskFolder, { recursive: true, force: true });
  }

  res.json({ success: clients[cIndex].tasks.length < beforeCount });
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
const upload = multer({
  storage,
  limits: {
    fileSize: 100 * 1024 * 1024 // 100 MB per file
  }
});


app.get("/progress", (req, res) => {
  res.setHeader("Content-Type", "text/event-stream");
  res.setHeader("Cache-Control", "no-cache");
  res.setHeader("Connection", "keep-alive");
  const interval = setInterval(
    () => res.write(`data: ${JSON.stringify(mergeProgress)}\n\n`),
    1000
  );
  req.on("close", () => clearInterval(interval));
});

app.post("/merge", requireAuth, upload.array("pdfs"), async (req, res) => {
  const { task_id } = req.body;
  if (!task_id) return res.status(400).json({ error: "Missing task_id" });
  if (!req.files || req.files.length === 0)
    return res.status(400).json({ error: "No files uploaded" });

  const taskPath = path.join(BASE_TASK_DIR, task_id);
  const inputDir = path.join(taskPath, "input_pdfs");
  const outputPath = path.join(taskPath, "merged_output.pdf");

  if (fs.existsSync(outputPath)) fs.unlinkSync(outputPath);

  mergeProgress = { percent: 10, message: "Starting merge..." };

  // 🟡 Mark task as in-progress (save to clients.json)
  const clients = loadClients();
  const currentClient = req.session.currentClient;
  const cIndex = clients.findIndex((c) => c.id === currentClient.id);
  const tIndex = clients[cIndex].tasks.findIndex((t) => t.id === task_id);

  if (tIndex !== -1) {
    clients[cIndex].tasks[tIndex].status = "in-progress";
    saveClients(clients);
  }

  // Pass client metadata to python
  const meta = JSON.stringify({
    tpName: currentClient.tpName,
    tpSSN: currentClient.tpSSN,
    spName: currentClient.spName,
    spSSN: currentClient.spSSN,
    taskId: task_id
  });

  try {
    const pythonPath = process.platform === "win32" ? "python" : "python3";
    const args = ["merge_with_bookmarks.py", inputDir, outputPath, meta];

    const python = spawn(pythonPath, args);

    python.stdout.on("data", (data) => {
      mergeProgress = { percent: 60, message: data.toString().trim() };
    });

    python.stderr.on("data", (data) => {
      console.error(`[PYTHON ERR] ${data}`);
    });

    python.on("close", (code) => {
      if (code === 0) {
        mergeProgress = { percent: 100, message: "Merge complete!" };

        // Save completed
        const clients = loadClients();
        const cIndex = clients.findIndex((c) => c.id === currentClient.id);
        const tIndex = clients[cIndex].tasks.findIndex((t) => t.id === task_id);

        if (tIndex !== -1) {
          clients[cIndex].tasks[tIndex].merged = true;
          clients[cIndex].tasks[tIndex].status = "completed";
          clients[cIndex].tasks[tIndex].date = new Date().toISOString();
          saveClients(clients);
        }

        return res.json({ success: true, task_id });
      }

      return res.status(500).json({ error: "Merge failed" });
    });

  } catch (err) {
    res.status(500).json({ error: "Internal error during merge" });
  }
});

// =============================
// File Download
// =============================
app.get("/download/:taskId", requireAuth, (req, res) => {
  const taskId = req.params.taskId;
  const mergedPath = path.join(BASE_TASK_DIR, taskId, "merged_output.pdf");
  if (!fs.existsSync(mergedPath))
    return res.status(404).send("Merged file not found.");
  res.download(mergedPath, `${taskId}_merged.pdf`);
});

// =============================
// Start Server
// =============================
app.listen(PORT, () => {
  console.log(`🚀 Server running at http://localhost:${PORT}/login.html`);
});
