// =========================
// upload.js — FINAL FIXED VERSION (Stable for multi-task & background merge)
// =========================

document.addEventListener("DOMContentLoaded", () => {
  const dropZone = document.getElementById("drop-zone");
  const fileInput = document.getElementById("file-input");
  const fileList = document.getElementById("file-list");
  const mergeBtn = document.getElementById("merge-btn");
  const backBtn = document.getElementById("back-btn");
  const progressContainer = document.getElementById("progress-container");
  const progressBar = document.getElementById("progress-bar");
  const progressMsg = document.getElementById("progress-msg");

  let selectedFiles = [];
  let mergeInProgress = false; // 🟢 Track if merge is ongoing

  // =========================
  // Drag & Drop Handlers
  // =========================
  dropZone.addEventListener("click", () => fileInput.click());

  ["dragenter", "dragover"].forEach(evt =>
    dropZone.addEventListener(evt, e => {
      e.preventDefault();
      dropZone.classList.add("dragover");
    })
  );

  ["dragleave", "drop"].forEach(evt =>
    dropZone.addEventListener(evt, e => {
      e.preventDefault();
      dropZone.classList.remove("dragover");
    })
  );

  dropZone.addEventListener("drop", e => handleFiles(Array.from(e.dataTransfer.files)));
  fileInput.addEventListener("change", e => handleFiles(Array.from(e.target.files)));

  // =========================
  // File Handling
  // =========================
  function handleFiles(files) {
    files.forEach(file => {
      if (file.size > 16 * 1024 * 1024) {
        alert(`${file.name} exceeds 16 MB limit`);
        return;
      }
      if (!selectedFiles.some(f => f.name === file.name)) {
        selectedFiles.push(file);
      }
    });
    renderFileList();
  }

  function renderFileList() {
    fileList.innerHTML = selectedFiles
      .map(
        (f, i) => `
        <div class="d-flex justify-content-between align-items-center border p-2 rounded mb-2 bg-light">
          <span>${f.name}</span>
          <button class="btn btn-sm btn-outline-danger" data-index="${i}">&times;</button>
        </div>`
      )
      .join("");

    fileList.querySelectorAll("button").forEach(btn => {
      btn.addEventListener("click", e => {
        const i = e.target.dataset.index;
        selectedFiles.splice(i, 1);
        renderFileList();
      });
    });
  }

  // =========================
  // Back Button
  // =========================
  backBtn.addEventListener("click", () => {
    // Allow silent return even during upload
    if (mergeInProgress) {
      console.log("⚙️ Merge still running in background — navigating quietly.");
    }
    window.location.href = "/task.html";
  });

  // =========================
  // Upload & Merge Handler
  // =========================
  mergeBtn.addEventListener("click", async () => {
    const taskId = new URLSearchParams(window.location.search).get("task");

    if (!taskId) {
      alert("❌ Missing task ID. Please open this page from the Task screen.");
      window.location.href = "/task.html";
      return;
    }

    if (selectedFiles.length === 0) {
      alert("Please select at least one file before merging.");
      return;
    }

    const formData = new FormData();
    formData.append("task_id", taskId);
    selectedFiles.forEach(f => formData.append("pdfs", f));

    // Show progress bar
    progressContainer.style.display = "block";
    progressBar.style.width = "0%";
    progressBar.innerText = "0%";
    progressMsg.innerText = "Uploading files and starting merge...";
    mergeInProgress = true;

    try {
      const controller = new AbortController();

      const response = await fetch("/merge", {
        method: "POST",
        body: formData,
        credentials: "include", // ✅ keeps session cookie
        signal: controller.signal
      });

      if (response.status === 401) {
        alert("⚠️ Session expired. Please log in again.");
        window.location.href = "/login.html";
        return;
      }

      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.error || "Failed to start merge.");
      }

      const result = await response.json();

      if (result.success) {
        progressBar.style.width = "100%";
        progressBar.innerText = "100%";
        progressMsg.innerText = "✅ Merge complete!";
        alert("✅ Merge started successfully! You can continue working on other tasks.");
        mergeInProgress = false;
        window.location.href = "/task.html";
      } else {
        throw new Error(result.error || "Merge failed.");
      }
    } catch (err) {
      // 🧩 Ignore abort/network errors from navigation
      if (err.name === "AbortError" || err.message === "Failed to fetch") {
        console.warn("⚠️ Navigation interrupted upload — ignoring error.");
        return;
      }

      console.error("❌ Merge error:", err);
      alert("❌ " + err.message);
      progressMsg.innerText = "Merge failed. Please try again.";
    } finally {
      mergeInProgress = false;
    }
  });

  // =========================
  // Future: Live progress polling
  // =========================
  /*
  setInterval(async () => {
    try {
      const res = await fetch("/progress");
      if (!res.ok) return;
      const data = await res.text();
      if (data.startsWith("data:")) {
        const json = JSON.parse(data.replace("data:", "").trim());
        progressBar.style.width = `${json.percent}%`;
        progressBar.innerText = `${json.percent}%`;
        progressMsg.innerText = json.message;
      }
    } catch {}
  }, 2000);
  */
});

