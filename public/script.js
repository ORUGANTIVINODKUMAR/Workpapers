// --- Element references ---
const dropZone   = document.getElementById('drop-zone');
const fileInput  = document.getElementById('file-input');
const fileList   = document.getElementById('file-list');
const mergeBtn   = document.getElementById('merge-btn');
const progressContainer = document.getElementById('progress-container');
const progressBar = document.getElementById('progress-bar');
const progressMsg = document.getElementById('progress-msg');


let selectedFiles = [];

// --- tsParticles init ---
tsParticles.load('tsparticles', {
  fullScreen: { enable: true, zIndex: -2 },
  background: { color: '#000000' },
  fpsLimit: 60,
  particles: {
    number: { value: 500, density: { enable: true, area: 800 } },
    color: { value: ['#007BFF'] },
    shape: { type: 'circle' },
    opacity: {
      value: 0.2,
      random: true,
      anim: { enable: true, speed: 0.7, opacity_min: 0.5 }
    },
    size: { value: 1, random: { enable: true, minimumValue: 1.5 } },
    move: {
      enable: true,
      speed: 2,
      random: true,
      outModes: { default: 'out' }
    },
    links: { enable: false }
  },
  interactivity: {
    detectsOn: 'window',
    events: {
      onHover: {
        enable: true,
        mode: 'connect',
        parallax: { enable: true, force: 100, smooth: 1 }
      },
      resize: true
    },
    modes: {
      connect: { distance: 50, links: { opacity: 0.3 }, radius: 50 }
    }
  }
});

// --- Utility: sync our array back to the <input> ---
function refreshInputFiles() {
  const dt = new DataTransfer();
  selectedFiles.forEach(f => dt.items.add(f));
  fileInput.files = dt.files;
}

// --- Utility: render file list with delete buttons ---
function updateFileList() {
  fileList.innerHTML = '';
  selectedFiles.forEach((file, idx) => {
    const item = document.createElement('div');
    item.className = 'file-item';
    item.innerHTML = `
      <span>${file.name}</span>
      <button class="delete-btn" data-index="${idx}" title="Remove">
        <i class="bi bi-x-circle-fill"></i>
      </button>
    `;
    fileList.appendChild(item);
  });

  // Attach delete handlers
  fileList.querySelectorAll('.delete-btn').forEach(btn => {
    btn.addEventListener('click', e => {
      const i = Number(e.currentTarget.dataset.index);
      selectedFiles.splice(i, 1);
      refreshInputFiles();
      updateFileList();
    });
  });
}

// --- Shared file processing (called by both drop and input) ---
function handleFiles(files) {
  files.forEach(file => {
    if (file.size > 16 * 1024 * 1024) {
      alert(`${file.name} is too large (max 16 MB).`);
      return;
    }
    // avoid duplicates by name
    if (!selectedFiles.some(f => f.name === file.name)) {
      selectedFiles.push(file);
    }
  });
  refreshInputFiles();
  updateFileList();
}

// --- Drag-and-drop handlers ---
['dragenter','dragover'].forEach(evt =>
  dropZone.addEventListener(evt, e => {
    e.preventDefault();
    dropZone.classList.add('dragover');
  })
);
['dragleave','dragend','drop'].forEach(evt =>
  dropZone.addEventListener(evt, e => {
    e.preventDefault();
    dropZone.classList.remove('dragover');
  })
);
dropZone.addEventListener('drop', e => {
  handleFiles(Array.from(e.dataTransfer.files));
});

// --- File-picker handler ---
fileInput.addEventListener('change', e => {
  handleFiles(Array.from(e.target.files));
  fileInput.value = ''; // allow same-file re-selection
});

// --- Merge & download action ---
mergeBtn.addEventListener('click', async () => {
  if (selectedFiles.length === 0) {
    return alert('Please select at least one file.');
  }

  const formData = new FormData();
  selectedFiles.forEach(f => formData.append('pdfs', f));

  // Reset and show progress bar
  progressContainer.style.display = "block";
  progressBar.style.width = "0%";
  progressBar.innerText = "0%";
  progressMsg.innerText = "Starting...";

  // Start listening for progress updates
  const evtSource = new EventSource('/progress');
  evtSource.onmessage = (event) => {
    const { percent, message } = JSON.parse(event.data);
    progressBar.style.width = percent + "%";
    progressBar.innerText = percent + "%";
    progressMsg.innerText = message;

    if (percent === 100) {
      evtSource.close();
    }
  };

  try {
    const response = await fetch('/merge', { method: 'POST', body: formData });
    if (!response.ok) throw new Error('Merge failed');

    const blob = await response.blob();
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = 'merged-with-bookmarks.pdf';
    document.body.appendChild(link);
    link.click();
    link.remove();

    progressMsg.innerText = "Download ready!";
  } catch (err) {
    alert(err.message);
    progressMsg.innerText = "Error during merge.";
  }
});

// --- Logout button handler ---
const logoutBtn = document.getElementById('logout-btn');
if (logoutBtn) {
  logoutBtn.addEventListener('click', async () => {
    try {
      await fetch('/logout', { method: 'POST' });
      window.location.href = '/login.html';
    } catch (err) {
      alert('Logout failed. Please try again.');
    }
  });
}

