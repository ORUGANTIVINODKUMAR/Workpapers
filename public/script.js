const input = document.getElementById('pdfFiles');
const fileList = document.getElementById('file-list');
const noFilesAlert =document.getElementById('no-files-alert');
let selectedFiles = [];

// Toggle file list dropdown on label click
document.querySelector('.upload-btn').addEventListener('click', () => {
  fileList.classList.toggle('d-none');
  });

// Handle file selection
input.addEventListener('change', () => {
  for (let file of input.files) {
    selectedFiles.push(file);
  }
  updateFileList();
  input.value = ''; // clear input to allow re-uploading same file
  if (selectedFiles.length > 0) {
    noFilesAlert.classList.add('d-none');
    fileList.classList.remove('d-none');
  }
});

// Display selected files in dropdown
function updateFileList() {
  fileList.innerHTML = '';
  selectedFiles.forEach((file, index) => {
    const item = document.createElement('div');
    item.className = 'file-item';
    item.innerHTML = `
      <span>${file.name}</span>
      <button onclick="removeFile(${index})">🗑️</button>
    `;
    fileList.appendChild(item);
  });
}

// Remove file by index
function removeFile(index) {
  selectedFiles.splice(index, 1);
  updateFileList();
  if (selectedFiles.length === 0)
  {
    fileList.classList.add('d-none');
  }
}

// Merge and Download Logic
async function mergePDFs() {
  if (selectedFiles.length === 0) {
    noFilesAlert.classList.remove('d-none');
    return;
  }

  const formData = new FormData();
  selectedFiles.forEach((file) => {
    formData.append('pdfs', file);
  });

 const response = await fetch('http://localhost:3001/merge', {
  method: 'POST',
  body: formData,
});


  if (!response.ok) {
    alert("Failed to merge PDFs");
    return;
  }

  const blob = await response.blob();
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.download = 'merged-with-bookmarks.pdf';
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}






