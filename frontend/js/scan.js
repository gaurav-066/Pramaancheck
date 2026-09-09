// PramaanCheck - Interactive Scan & Canvas Corner Calibration Script

let selectedFile = null;
let originalImage = null;
let canvasPoints = []; // Clicked canvas points [{x, y}]
let scaleFactor = 1.0;

document.addEventListener('DOMContentLoaded', async () => {
  // Check auth session
  const currentUser = await getCurrentUser();
  if (!currentUser) {
    window.location.href = '/login';
    return;
  }

  // Populate user badge in navbar
  document.getElementById('user-name').textContent = currentUser.name || currentUser.username;
  const roleElem = document.getElementById('user-role');
  roleElem.textContent = currentUser.role;
  roleElem.className = `user-role-tag role-${currentUser.role}`;

  // Setup drag & drop handlers
  const dropZone = document.getElementById('drop-zone');
  if (dropZone) {
    dropZone.addEventListener('dragover', (e) => {
      e.preventDefault();
      dropZone.classList.add('dragover');
    });
    dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));
    dropZone.addEventListener('drop', (e) => {
      e.preventDefault();
      dropZone.classList.remove('dragover');
      if (e.dataTransfer.files.length > 0) {
        handleFile(e.dataTransfer.files[0]);
      }
    });
  }

  // Canvas click listener for reference card corners
  const canvas = document.getElementById('label-canvas');
  if (canvas) {
    canvas.addEventListener('click', onCanvasClick);
  }
});

function handleFileSelect(event) {
  if (event.target.files.length > 0) {
    handleFile(event.target.files[0]);
  }
}

function handleFile(file) {
  selectedFile = file;
  document.getElementById('start-scan-btn').disabled = false;
  document.getElementById('calibration-section').style.display = 'block';

  // Load image onto Canvas
  const reader = new FileReader();
  reader.onload = (e) => {
    const img = new Image();
    img.onload = () => {
      originalImage = img;
      canvasPoints = [];
      renderCanvas();
    };
    img.src = e.target.result;
  };
  reader.readAsDataURL(file);
}

function renderCanvas() {
  if (!originalImage) return;

  const canvas = document.getElementById('label-canvas');
  const ctx = canvas.getContext('2d');

  // Constrain max canvas display width to 600px
  const maxCanvasWidth = 600;
  scaleFactor = Math.min(1.0, maxCanvasWidth / originalImage.width);

  canvas.width = originalImage.width * scaleFactor;
  canvas.height = originalImage.height * scaleFactor;

  // Draw background image
  ctx.drawImage(originalImage, 0, 0, canvas.width, canvas.height);

  // Draw clicked corner points & connecting polygon
  if (canvasPoints.length > 0) {
    ctx.strokeStyle = '#06b6d4';
    ctx.lineWidth = 2;
    ctx.fillStyle = 'rgba(6, 182, 212, 0.25)';

    ctx.beginPath();
    ctx.moveTo(canvasPoints[0].x, canvasPoints[0].y);
    for (let i = 1; i < canvasPoints.length; i++) {
      ctx.lineTo(canvasPoints[i].x, canvasPoints[i].y);
    }
    if (canvasPoints.length === 4) {
      ctx.closePath();
      ctx.fill();
    }
    ctx.stroke();

    // Draw point markers
    canvasPoints.forEach((pt, idx) => {
      ctx.fillStyle = '#06b6d4';
      ctx.beginPath();
      ctx.arc(pt.x, pt.y, 6, 0, 2 * Math.PI);
      ctx.fill();
      ctx.fillStyle = '#000';
      ctx.font = 'bold 10px sans-serif';
      ctx.fillText(idx + 1, pt.x - 3, pt.y + 3);
    });
  }

  // Update status labels
  const pointsCountElem = document.getElementById('points-count');
  const statusElem = document.getElementById('canvas-status');
  pointsCountElem.textContent = `${canvasPoints.length} / 4 points marked`;

  if (canvasPoints.length === 4) {
    statusElem.textContent = 'Status: ID Card Scale Calibrated (85.6mm)';
    statusElem.style.color = 'var(--status-pass-text)';
  } else {
    statusElem.textContent = 'Status: Default Scale (Heuristic)';
    statusElem.style.color = 'var(--text-secondary)';
  }
}

function onCanvasClick(e) {
  if (!originalImage || canvasPoints.length >= 4) return;

  const canvas = document.getElementById('label-canvas');
  const rect = canvas.getBoundingClientRect();
  const x = e.clientX - rect.left;
  const y = e.clientY - rect.top;

  canvasPoints.push({ x, y });
  renderCanvas();
}

function resetCanvasCorners() {
  canvasPoints = [];
  renderCanvas();
}

async function runLabelScan() {
  if (!selectedFile) return;

  const scanAlert = document.getElementById('scan-alert');
  scanAlert.style.display = 'none';

  document.getElementById('results-placeholder').style.display = 'none';
  document.getElementById('results-content').style.display = 'none';
  document.getElementById('loading-spinner').style.display = 'block';

  // Prepare FormData
  const formData = new FormData();
  formData.append('file', selectedFile);

  // If 4 points marked, convert canvas points to original image coordinates
  if (canvasPoints.length === 4) {
    const originalPoints = canvasPoints.map(pt => [
      Math.round(pt.x / scaleFactor),
      Math.round(pt.y / scaleFactor)
    ]);
    formData.append('card_corners', JSON.stringify(originalPoints));
  }

  try {
    const response = await fetch('/api/scan', {
      method: 'POST',
      credentials: 'same-origin',
      body: formData
    });

    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || 'Scan processing failed');
    }

    renderScanResults(data);
  } catch (err) {
    scanAlert.textContent = err.message;
    scanAlert.style.display = 'block';
    document.getElementById('results-placeholder').style.display = 'block';
  } finally {
    document.getElementById('loading-spinner').style.display = 'none';
  }
}

function renderScanResults(data) {
  document.getElementById('results-content').style.display = 'block';

  // Render Overall Status Badge
  const statusBadge = document.getElementById('res-status-badge');
  const status = data.overall_status;
  if (status === 'COMPLIANT') {
    statusBadge.className = 'badge badge-pass';
    statusBadge.textContent = '✓ COMPLIANT';
  } else if (status === 'WARNING') {
    statusBadge.className = 'badge badge-warn';
    statusBadge.textContent = '⚠ WARNING';
  } else {
    statusBadge.className = 'badge badge-fail';
    statusBadge.textContent = '✕ NON COMPLIANT';
  }

  // Render Score
  document.getElementById('res-score-val').textContent = `${data.compliance_score}%`;

  // Render OCR Engine Tag
  const ocrEngineElem = document.getElementById('res-ocr-engine');
  if (ocrEngineElem) {
    const engineUsed = data.declarations?.ocr_engine || 'unknown';
    if (engineUsed.includes('gemini')) {
      ocrEngineElem.textContent = `✨ ${engineUsed.toUpperCase()}`;
      ocrEngineElem.style.color = 'var(--accent-cyan)';
    } else {
      ocrEngineElem.textContent = `⚙️ TESSERACT OCR (FALLBACK)`;
      ocrEngineElem.style.color = 'var(--status-warn-text)';
    }
  }

  // Render Font Check Details
  const fontCheck = data.font_check || {};
  document.getElementById('res-font-details').textContent = fontCheck.rule_7_details || 'Font height verified.';

  // Render Rules Checklist
  const rulesList = document.getElementById('rules-list');
  rulesList.innerHTML = '';

  const rules = data.rule_results?.rules || [];
  rules.forEach(rule => {
    const ruleDiv = document.createElement('div');
    ruleDiv.className = 'rule-item';

    let badgeClass = 'badge-pass';
    let icon = '✓';
    if (rule.status === 'FAIL') {
      badgeClass = 'badge-fail';
      icon = '✕';
    } else if (rule.status === 'WARNING') {
      badgeClass = 'badge-warn';
      icon = '⚠';
    }

    ruleDiv.innerHTML = `
      <div class="rule-info">
        <div class="rule-title">
          <span>${rule.rule_name}</span>
          <span class="rule-section">${rule.act_section || 'Rule 6'}</span>
        </div>
        <div class="rule-details">${rule.details}</div>
      </div>
      <span class="badge ${badgeClass}">${icon} ${rule.status}</span>
    `;

    rulesList.appendChild(ruleDiv);
  });

  // PDF Report Download Button (if scan_id present)
  const downloadBtn = document.getElementById('download-report-btn');
  if (data.scan_id) {
    downloadBtn.href = `/api/reports/download/${data.scan_id}`;
    downloadBtn.style.display = 'flex';
  }
}
