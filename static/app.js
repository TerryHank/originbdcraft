// === BeadCraft Frontend Application ===

// Global state
window.appState = {
  originalImage: null,
  pixelMatrix: null,
  colorData: {},
  colorSummary: [],
  fullPalette: {},         // code -> {hex, name, ...} for ALL 221 colors
  fullPaletteList: [],     // ordered array of all colors
  presets: {},             // preset definitions from server
  palettePreset: '221',   // current preset key
  gridSize: { width: 0, height: 0 },
  activeColors: new Set(),
  editMode: false,
  sessionId: null,
  totalBeads: 0,
};

// === Clear Canvas ===
function clearCanvas() {
  // Reset state
  window.appState.originalImage = null;
  window.appState.pixelMatrix = null;
  window.appState.colorData = {};
  window.appState.colorSummary = [];
  window.appState.gridSize = { width: 0, height: 0 };
  window.appState.activeColors = new Set();

  // Hide canvas, show empty-state
  document.getElementById('pattern-canvas').style.display = 'none';
  document.getElementById('color-panel').style.display = 'none';
  document.getElementById('empty-state').classList.remove('hidden');

  // Clear canvas
  const canvas = document.getElementById('pattern-canvas');
  const ctx = canvas.getContext('2d');
  ctx.clearRect(0, 0, canvas.width, canvas.height);

  // Hide settings panel
  document.getElementById('settings-panel').style.display = 'none';
}

// === Initialization ===
document.addEventListener('DOMContentLoaded', () => {
  loadFullPalette();
  initUpload();
  initTabs();
  initControls();
  applyTranslations();
  
  // Auto-scan and select serial port (ESP32/CH340/CP210x)
  refreshSerialPorts(true);
  
  // Auto-generate pattern when LED size changes
  const ledSizeSelect = document.getElementById('led-matrix-size');
  if (ledSizeSelect) {
    ledSizeSelect.addEventListener('change', () => {
      if (window.appState.originalImage) {
        generatePattern();
      }
    });
  }
});

// === Load Example Image ===
async function loadExampleImage(name) {
  try {
    // Fetch the original image
    const response = await fetch(`/examples/${name}_original.jpg`);
    if (!response.ok) {
      showToast(t('toast.example_load_error'), true);
      return;
    }

    const blob = await response.blob();
    const file = new File([blob], `${name}_original.jpg`, { type: 'image/jpeg' });

    // Set as original image and generate directly
    window.appState.originalImage = file;
    document.getElementById('empty-state').classList.add('hidden');
    document.getElementById('settings-panel').style.display = 'block';
    
    // Generate pattern directly
    await generatePattern();

  } catch (err) {
    showToast(t('toast.example_load_error'), true);
  }
}

async function loadFullPalette() {
  try {
    const resp = await fetch('/api/palette');
    if (resp.ok) {
      const data = await resp.json();
      const colors = data.colors || [];
      window.appState.fullPaletteList = colors;
      colors.forEach(c => {
        window.appState.fullPalette[c.code] = c;
      });
      window.appState.presets = data.presets || {};
    }
  } catch (e) {
    console.error('Failed to load palette', e);
  }
}

// === Get current preset color list for edit popover ===
function getPresetColorList() {
  const { presets, palettePreset, fullPaletteList, fullPalette } = window.appState;
  const preset = presets[palettePreset];
  if (!preset || !preset.codes) {
    return fullPaletteList;
  }
  return preset.codes
    .map(code => fullPalette[code])
    .filter(c => c != null);
}

// === Preset Selection ===
function setPreset(key) {
  window.appState.palettePreset = key;
  document.querySelectorAll('.preset-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.preset === key);
  });
}

// === Toast Notifications ===
function showToast(message, isError = false) {
  const container = document.getElementById('toast-container');
  const toast = document.createElement('div');
  toast.className = 'toast' + (isError ? ' error' : '');
  toast.textContent = message;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transition = 'opacity 0.3s';
    setTimeout(() => toast.remove(), 300);
  }, 3000);
}

// === File Upload ===
function initUpload() {
  const input = document.getElementById('file-input');

  input.addEventListener('change', () => {
    if (input.files.length > 0) {
      const file = input.files[0];
      input.value = '';  // Reset so user can select same file again
      handleFile(file);
    }
  });
}

function handleFile(file) {
  // Validate type
  const validTypes = ['image/jpeg', 'image/png', 'image/gif', 'image/webp'];
  if (!validTypes.includes(file.type)) {
    showToast(t('toast.upload_type_error'), true);
    return;
  }

  // Validate size (20MB)
  if (file.size > 20 * 1024 * 1024) {
    showToast(t('toast.upload_size_error'), true);
    return;
  }

  // Show crop dialog
  showCropDialog(file);
}

// === Image Crop ===
let cropState = {
  file: null,
  img: null,
  scale: 1,
  box: { x: 0, y: 0, size: 0 },
  dragging: false,
  startX: 0,
  startY: 0,
};

function showCropDialog(file) {
  cropState.file = file;
  
  const reader = new FileReader();
  reader.onload = (e) => {
    const img = new Image();
    img.onload = () => {
      cropState.img = img;
      
      const cropImg = document.getElementById('crop-image');
      cropImg.src = e.target.result;
      
      // Calculate display scale
      const container = document.getElementById('crop-container');
      const maxW = window.innerWidth * 0.85;
      const maxH = window.innerHeight * 0.65;
      cropState.scale = Math.min(maxW / img.width, maxH / img.height, 1);
      
      cropImg.style.width = (img.width * cropState.scale) + 'px';
      cropImg.style.height = (img.height * cropState.scale) + 'px';
      
      // Initialize crop box (square based on min dimension)
      const minDim = Math.min(img.width, img.height);
      cropState.box.size = minDim;
      cropState.box.x = (img.width - minDim) / 2;
      cropState.box.y = (img.height - minDim) / 2;
      
      updateCropBox();
      
      // Show dialog
      document.getElementById('crop-dialog').style.display = 'flex';
      
      // Setup drag
      setupCropDrag();
    };
    img.src = e.target.result;
  };
  reader.readAsDataURL(file);
}

function updateCropBox() {
  const box = document.getElementById('crop-box');
  const scale = cropState.scale;
  box.style.left = (cropState.box.x * scale) + 'px';
  box.style.top = (cropState.box.y * scale) + 'px';
  box.style.width = (cropState.box.size * scale) + 'px';
  box.style.height = (cropState.box.size * scale) + 'px';
}

function setupCropDrag() {
  const box = document.getElementById('crop-box');
  
  box.onmousedown = (e) => {
    e.preventDefault();
    cropState.dragging = true;
    cropState.startX = e.clientX - cropState.box.x * cropState.scale;
    cropState.startY = e.clientY - cropState.box.y * cropState.scale;
  };
  
  document.onmousemove = (e) => {
    if (!cropState.dragging) return;
    
    let newX = (e.clientX - cropState.startX) / cropState.scale;
    let newY = (e.clientY - cropState.startY) / cropState.scale;
    
    // Clamp to image bounds
    const img = cropState.img;
    const size = cropState.box.size;
    newX = Math.max(0, Math.min(newX, img.width - size));
    newY = Math.max(0, Math.min(newY, img.height - size));
    
    cropState.box.x = newX;
    cropState.box.y = newY;
    updateCropBox();
  };
  
  document.onmouseup = () => {
    cropState.dragging = false;
  };
}

function cancelCrop() {
  document.getElementById('crop-dialog').style.display = 'none';
  cropState = { file: null, img: null, scale: 1, box: { x: 0, y: 0, size: 0 }, dragging: false };
}

function confirmCrop() {
  const img = cropState.img;
  const box = cropState.box;
  
  // Create canvas and crop
  const canvas = document.createElement('canvas');
  canvas.width = box.size;
  canvas.height = box.size;
  const ctx = canvas.getContext('2d');
  ctx.drawImage(img, box.x, box.y, box.size, box.size, 0, 0, box.size, box.size);
  
  // Convert to blob
  canvas.toBlob((blob) => {
    const croppedFile = new File([blob], cropState.file.name, { type: 'image/jpeg' });
    window.appState.originalImage = croppedFile;
    
    // Close dialog
    cancelCrop();
    
    // Hide empty-state and generate directly
    document.getElementById('empty-state').classList.add('hidden');
    document.getElementById('settings-panel').style.display = 'block';
    
    // Generate pattern directly
    generatePattern();
  }, 'image/jpeg', 0.95);
}

// === Tab Switching ===
function initTabs() {
  document.querySelectorAll('.tab-group').forEach(group => {
    group.querySelectorAll('.tab-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const target = btn.dataset.target;
        const parent = btn.closest('.tab-group');

        // Update tab buttons
        parent.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');

        // Show/hide content
        const contents = parent.nextElementSibling?.parentElement?.querySelectorAll('.tab-content');
        if (contents) {
          contents.forEach(c => {
            c.style.display = c.id === target ? 'block' : 'none';
          });
        }
      });
    });
  });
}

// === Controls ===
function initControls() {
  // Pixel size slider
  const pixelSlider = document.getElementById('pixel-size-slider');
  const pixelValue = document.getElementById('pixel-size-value');
  if (pixelSlider) {
    pixelSlider.addEventListener('input', () => {
      pixelValue.textContent = pixelSlider.value + 'px';
    });
  }

  // Max colors slider
  const maxColorsSlider = document.getElementById('max-colors-slider');
  const maxColorsValue = document.getElementById('max-colors-value');
  if (maxColorsSlider) {
    maxColorsSlider.addEventListener('input', () => {
      const v = parseInt(maxColorsSlider.value);
      maxColorsValue.textContent = v === 0 ? t('value.auto') : v;
    });
  }

  // Similarity threshold slider
  const simSlider = document.getElementById('similarity-slider');
  const simValue = document.getElementById('similarity-value');
  if (simSlider) {
    simSlider.addEventListener('input', () => {
      const v = parseInt(simSlider.value);
      simValue.textContent = v === 0 ? t('value.off') : v;
    });
  }

  // Contrast slider
  const contrastSlider = document.getElementById('contrast-slider');
  const contrastValue = document.getElementById('contrast-value');
  if (contrastSlider) {
    contrastSlider.addEventListener('input', () => {
      const v = parseInt(contrastSlider.value);
      contrastValue.textContent = v === 0 ? t('value.auto') : (v > 0 ? '+' + v : v);
    });
  }

  // Saturation slider
  const satSlider = document.getElementById('saturation-slider');
  const satValue = document.getElementById('saturation-value');
  if (satSlider) {
    satSlider.addEventListener('input', () => {
      const v = parseInt(satSlider.value);
      satValue.textContent = v === 0 ? t('value.auto') : (v > 0 ? '+' + v : v);
    });
  }

  // Sharpness slider
  const sharpSlider = document.getElementById('sharpness-slider');
  const sharpValue = document.getElementById('sharpness-value');
  if (sharpSlider) {
    sharpSlider.addEventListener('input', () => {
      const v = parseInt(sharpSlider.value);
      sharpValue.textContent = v === 0 ? t('value.auto') : (v > 0 ? '+' + v : v);
    });
  }

  // Generate button
  const genBtn = document.getElementById('generate-btn');
  if (genBtn) {
    genBtn.addEventListener('click', generatePattern);
  }
}

// === Grid Mode Toggle ===
function setGridMode(mode) {
  document.getElementById('grid-fixed-options').style.display = mode === 'fixed' ? 'block' : 'none';
  document.getElementById('grid-pixel-options').style.display = mode === 'pixel' ? 'block' : 'none';
}

// === Generate Pattern ===
async function generatePattern() {
  if (!window.appState.originalImage) {
    showToast(t('toast.upload_first'), true);
    return;
  }

  // Build form data
  const formData = new FormData();
  formData.append('file', window.appState.originalImage);

  // Get difficulty setting
  const gridSelect = document.getElementById('grid-size-select');
  const difficulty = gridSelect?.value || 'normal';
  
  // Get original image dimensions
  const img = window.appState.originalImage;
  const imgWidth = img.width || img.naturalWidth || 512;
  const imgHeight = img.height || img.naturalHeight || 512;
  
  // Calculate scale based on difficulty
  let scale;
  if (difficulty === 'simple') {
    scale = 0.25;  // 1/4 resolution
  } else if (difficulty === 'normal') {
    scale = 0.5;   // 1/2 resolution
  } else { // hard
    scale = 1.0;   // original resolution
  }
  
  // Calculate grid size based on original image and difficulty
  const gridWidth = Math.max(16, Math.round(imgWidth * scale));
  const gridHeight = Math.max(16, Math.round(imgHeight * scale));
  
  // LED size for ESP32 display
  const ledSize = parseInt(document.getElementById('led-matrix-size').value) || 64;
  
  formData.append('mode', 'fixed_grid');
  formData.append('grid_width', gridWidth);
  formData.append('grid_height', gridHeight);
  formData.append('led_size', ledSize);

  // Dithering (disabled by default)
  const dithering = document.getElementById('dithering-checkbox')?.checked || false;
  formData.append('use_dithering', dithering);

  // Palette preset
  formData.append('palette_preset', window.appState.palettePreset);

  // Max colors (0 = unlimited)
  const maxColorsSlider = document.getElementById('max-colors-slider');
  const maxColors = maxColorsSlider ? parseInt(maxColorsSlider.value) : 0;
  formData.append('max_colors', maxColors);

  // Similarity threshold (0 = disabled)
  const simSlider = document.getElementById('similarity-slider');
  const simThreshold = simSlider ? parseInt(simSlider.value) : 0;
  formData.append('similarity_threshold', simThreshold);

  // Background removal
  const removeBg = document.getElementById('remove-bg-checkbox')?.checked || false;
  formData.append('remove_bg', removeBg);

  // Image adjustments
  const contrastVal = document.getElementById('contrast-slider')?.value || 0;
  formData.append('contrast', contrastVal);
  const saturationVal = document.getElementById('saturation-slider')?.value || 0;
  formData.append('saturation', saturationVal);
  const sharpnessVal = document.getElementById('sharpness-slider')?.value || 0;
  formData.append('sharpness', sharpnessVal);

  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 60000);

    const response = await fetch('/api/generate', {
      method: 'POST',
      body: formData,
      signal: controller.signal,
    });

    clearTimeout(timeoutId);

    if (!response.ok) {
      const err = await response.json();
      throw new Error(err.detail || 'Generation failed');
    }

    const data = await response.json();

    // Update state
    window.appState.sessionId = data.session_id;
    window.appState.pixelMatrix = data.pixel_matrix;
    window.appState.gridSize = data.grid_size;
    window.appState.colorSummary = data.color_summary;
    window.appState.totalBeads = data.total_beads;
    window.appState.activeColors = new Set();
    window.appState.editMode = false;
    window.appState.palettePreset = data.palette_preset || '221';

    // Build colorData lookup (include fullPalette fallback)
    window.appState.colorData = {};
    data.color_summary.forEach(c => {
      window.appState.colorData[c.code] = c;
    });

    // Render result: show canvas, hide empty-state, show color panel
    document.getElementById('empty-state').classList.add('hidden');
    document.getElementById('pattern-canvas').style.display = 'block';
    document.getElementById('color-panel').style.display = 'block';
    renderCanvas();
    renderColorPanel();

    showToast(t('toast.pattern_result', { w: data.grid_size.width, h: data.grid_size.height, c: data.color_summary.length }));

    // Auto-send to ESP32 via serial
    await autoSendToESP32();

  } catch (err) {
    if (err.name === 'AbortError') {
      showToast(t('toast.timeout'), true);
    } else {
      showToast(err.message, true);
    }
  }
}

// === Auto Send to ESP32 after generation ===
async function autoSendToESP32() {
  const { pixelMatrix, connectionMode } = window.appState;
  if (!pixelMatrix) return;

  const bgColor = document.getElementById('serial-bg-color')?.value || '#000000';
  const bgRgb = [
    parseInt(bgColor.slice(1, 3), 16),
    parseInt(bgColor.slice(3, 5), 16),
    parseInt(bgColor.slice(5, 7), 16),
  ];

  // Show toast
  const toast = document.getElementById('serial-toast');
  if (toast) {
    toast.textContent = connectionMode === 'ble' ? 'Connecting via Bluetooth...' : t('serial.sending');
    toast.className = 'serial-toast';
    toast.style.display = 'block';
  }

  try {
    let result;
    
    if (connectionMode === 'ble') {
      // BLE mode
      const deviceAddress = document.getElementById('ble-device-select')?.value;
      if (!deviceAddress) {
        showToast('Please select a BLE device in settings', true);
        if (toast) toast.style.display = 'none';
        return;
      }
      
      const response = await fetch('/api/ble/send', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          pixel_matrix: pixelMatrix,
          device_address: deviceAddress,
          background_color: bgRgb,
        }),
      });
      result = await response.json();
    } else {
      // Serial mode (default)
      const port = document.getElementById('serial-port-select')?.value;
      if (!port) {
        showToast('Please select a serial port in settings', true);
        if (toast) toast.style.display = 'none';
        return;
      }
      
      const baudRate = parseInt(document.getElementById('serial-baud-select')?.value) || 460800;
      const ledSize = document.getElementById('led-matrix-size')?.value || '64';
      const ledMatrixSize = `${ledSize}x${ledSize}`;  // Format as "64x64"
      
      const response = await fetch('/api/serial/send', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          pixel_matrix: pixelMatrix,
          port: port,
          baud_rate: baudRate,
          background_color: bgRgb,
          led_matrix_size: ledMatrixSize,
        }),
      });
      result = await response.json();
    }

    if (result.success) {
      if (toast) {
        toast.textContent = `Sent ${result.bytes_sent} bytes in ${result.duration_ms}ms`;
        toast.className = 'serial-toast success';
      }
      showToast(connectionMode === 'ble' ? 'Image sent via Bluetooth!' : t('serial.send_success'));
    } else {
      if (toast) {
        toast.textContent = result.message;
        toast.className = 'serial-toast error';
      }
    }

    // Hide toast after 3s
    setTimeout(() => {
      if (toast) toast.style.display = 'none';
    }, 3000);

  } catch (err) {
    if (toast) {
      toast.textContent = err.message;
      toast.className = 'serial-toast error';
      setTimeout(() => {
        toast.style.display = 'none';
      }, 3000);
    }
  }
}

// === Canvas Rendering ===
function renderCanvas() {
  const canvas = document.getElementById('pattern-canvas');
  if (!canvas || !window.appState.pixelMatrix) return;

  const { pixelMatrix, gridSize, activeColors, colorData } = window.appState;
  const ctx = canvas.getContext('2d');

  // Calculate cell size to fit in 640x640 (including coord area)
  const coordSize = 20;
  const maxPatternDim = 600;
  const cellSize = Math.min(
    Math.floor(maxPatternDim / gridSize.width),
    Math.floor(maxPatternDim / gridSize.height)
  );
  const cs = Math.max(cellSize, 2);

  const patternW = gridSize.width * cs;
  const patternH = gridSize.height * cs;

  canvas.width = coordSize + patternW + coordSize;
  canvas.height = coordSize + patternH + coordSize;

  // Store layout info for click handling
  canvas._cellSize = cs;
  canvas._coordSize = coordSize;

  // Clear
  ctx.fillStyle = '#FFFFFF';
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  const ox = coordSize;
  const oy = coordSize;

  // --- Draw coordinate axes ---
  ctx.font = `${Math.max(7, cs / 3)}px monospace`;
  ctx.fillStyle = '#888888';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';

  for (let x = 0; x < gridSize.width; x++) {
    // Top (1 -> N)
    ctx.fillText(String(x + 1), ox + x * cs + cs / 2, oy - 10);
    // Bottom (N -> 1, reversed)
    ctx.fillText(String(gridSize.width - x), ox + x * cs + cs / 2, oy + patternH + 10);
  }
  for (let y = 0; y < gridSize.height; y++) {
    // Left
    ctx.fillText(String(y + 1), ox - 10, oy + y * cs + cs / 2);
    // Right
    ctx.fillText(String(y + 1), ox + patternW + 10, oy + y * cs + cs / 2);
  }

  // --- Draw cells ---
  const showCodes = cs >= 16;

  for (let y = 0; y < gridSize.height; y++) {
    for (let x = 0; x < gridSize.width; x++) {
      const code = pixelMatrix[y][x];
      const cx = ox + x * cs;
      const cy = oy + y * cs;

      if (code === null) {
        // Transparent: checkerboard
        const bk = Math.max(2, Math.floor(cs / 4));
        for (let by = 0; by < cs; by += bk) {
          for (let bx = 0; bx < cs; bx += bk) {
            const ix = Math.floor(bx / bk);
            const iy = Math.floor(by / bk);
            ctx.fillStyle = (ix + iy) % 2 === 0 ? '#DCDCDC' : '#B4B4B4';
            ctx.fillRect(cx + bx, cy + by, Math.min(bk, cs - bx), Math.min(bk, cs - by));
          }
        }
      } else {
        const info = colorData[code] || window.appState.fullPalette[code];
        const hex = info ? info.hex : '#FFFFFF';

        ctx.fillStyle = hex;
        ctx.fillRect(cx, cy, cs, cs);

        // Highlight mask
        if (activeColors.size > 0 && !activeColors.has(code)) {
          ctx.fillStyle = 'rgba(255, 255, 255, 0.72)';
          ctx.fillRect(cx, cy, cs, cs);
        }

        // Draw code text inside cell
        if (showCodes) {
          const r = parseInt(hex.slice(1, 3), 16) || 255;
          const g = parseInt(hex.slice(3, 5), 16) || 255;
          const b = parseInt(hex.slice(5, 7), 16) || 255;
          const brightness = (r * 299 + g * 587 + b * 114) / 1000;
          ctx.fillStyle = brightness > 128 ? '#000000' : '#FFFFFF';
          ctx.font = `bold ${Math.max(6, cs * 0.38)}px monospace`;
          ctx.textAlign = 'center';
          ctx.textBaseline = 'middle';
          ctx.fillText(code, cx + cs / 2, cy + cs / 2);
        }
      }
    }
  }

  // --- Draw grid lines ---
  if (cs >= 4) {
    ctx.strokeStyle = 'rgba(0, 0, 0, 0.1)';
    ctx.lineWidth = 0.5;

    for (let x = 0; x <= gridSize.width; x++) {
      ctx.beginPath();
      ctx.moveTo(ox + x * cs, oy);
      ctx.lineTo(ox + x * cs, oy + patternH);
      ctx.stroke();
    }
    for (let y = 0; y <= gridSize.height; y++) {
      ctx.beginPath();
      ctx.moveTo(ox, oy + y * cs);
      ctx.lineTo(ox + patternW, oy + y * cs);
      ctx.stroke();
    }
  }
}

// === Canvas Click Handling ===
document.addEventListener('DOMContentLoaded', () => {
  const canvas = document.getElementById('pattern-canvas');
  if (!canvas) return;

  canvas.addEventListener('click', (e) => {
    if (!window.appState.editMode || !window.appState.pixelMatrix) return;

    const rect = canvas.getBoundingClientRect();
    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;

    const canvasX = (e.clientX - rect.left) * scaleX;
    const canvasY = (e.clientY - rect.top) * scaleY;

    const cellSize = canvas._cellSize || 10;
    const coordSize = canvas._coordSize || 20;
    const col = Math.floor((canvasX - coordSize) / cellSize);
    const row = Math.floor((canvasY - coordSize) / cellSize);

    if (row >= 0 && row < window.appState.gridSize.height &&
        col >= 0 && col < window.appState.gridSize.width) {
      showColorPopover(e.clientX, e.clientY, row, col);
    }
  });

  // Hover effect in edit mode
  canvas.addEventListener('mousemove', (e) => {
    if (!window.appState.editMode || !window.appState.pixelMatrix) {
      canvas.style.cursor = 'default';
      return;
    }
    canvas.style.cursor = 'crosshair';
  });
});

// === Color Popover ===
function showColorPopover(clientX, clientY, row, col) {
  // Remove existing popover
  closeColorPopover();

  const popover = document.createElement('div');
  popover.className = 'color-popover';
  popover.id = 'color-popover';

  // Position
  popover.style.left = clientX + 'px';
  popover.style.top = clientY + 'px';

  // Adjust if near edge
  const maxLeft = window.innerWidth - 220;
  const maxTop = window.innerHeight - 260;
  if (clientX > maxLeft) popover.style.left = maxLeft + 'px';
  if (clientY > maxTop) popover.style.top = maxTop + 'px';

  // Current cell info
  const currentCode = window.appState.pixelMatrix[row][col];

  // Add color options from current preset (all colors in preset, not just used ones)
  const presetColors = getPresetColorList();
  presetColors.forEach(item => {
    const opt = document.createElement('div');
    opt.className = 'color-popover-item';
    if (item.code === currentCode) {
      opt.style.background = 'var(--accent-light)';
    }
    opt.innerHTML = `
      <span class="color-swatch" style="background: ${item.hex}"></span>
      <span style="font-weight: 600">${item.code}</span>
      <span style="color: var(--text-secondary)">${item.name}</span>
    `;
    opt.addEventListener('click', () => {
      updateCell(row, col, item.code);
      closeColorPopover();
    });
    popover.appendChild(opt);
  });

  document.body.appendChild(popover);

  // Close on outside click
  setTimeout(() => {
    document.addEventListener('click', outsideClickHandler);
  }, 10);
}

function outsideClickHandler(e) {
  const popover = document.getElementById('color-popover');
  if (popover && !popover.contains(e.target)) {
    closeColorPopover();
  }
}

function closeColorPopover() {
  const existing = document.getElementById('color-popover');
  if (existing) existing.remove();
  document.removeEventListener('click', outsideClickHandler);
}

// === Update Cell ===
async function updateCell(row, col, newCode) {
  const { pixelMatrix, sessionId } = window.appState;
  const oldCode = pixelMatrix[row][col];
  if (oldCode === newCode) return;

  // Update locally first for instant feedback
  pixelMatrix[row][col] = newCode;
  renderCanvas();

  // Sync with server
  try {
    const response = await fetch('/api/update_cell', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: sessionId,
        row: row,
        col: col,
        new_code: newCode,
      }),
    });

    if (response.ok) {
      const data = await response.json();
      window.appState.colorSummary = data.color_summary;
      window.appState.totalBeads = data.total_beads;

      // Rebuild colorData
      window.appState.colorData = {};
      data.color_summary.forEach(c => {
        window.appState.colorData[c.code] = c;
      });

      renderColorPanel();
    }
  } catch (err) {
    // Revert on error
    pixelMatrix[row][col] = oldCode;
    renderCanvas();
    showToast(t('toast.update_failed'), true);
  }
}

// === Color Panel ===
function renderColorPanel() {
  const list = document.getElementById('color-list');
  const total = document.getElementById('color-total');
  if (!list) return;

  list.innerHTML = '';

  window.appState.colorSummary.forEach(item => {
    const tag = document.createElement('div');
    tag.className = 'color-tag' + (window.appState.activeColors.has(item.code) ? ' active' : '');
    tag.dataset.code = item.code;
    tag.title = `${item.name} (${item.code})`;
    tag.innerHTML = `
      <span class="color-swatch" style="background: ${item.hex}"></span>
    `;

    tag.addEventListener('click', () => {
      toggleColorHighlight(item.code);
    });

    list.appendChild(tag);
  });

  if (total) {
    total.textContent = t('result.colors_total', { colors: window.appState.colorSummary.length, beads: window.appState.totalBeads });
  }
}

// === Color Highlight Toggle ===
function toggleColorHighlight(code) {
  const { activeColors } = window.appState;

  if (activeColors.has(code)) {
    activeColors.delete(code);
  } else {
    activeColors.add(code);
  }

  // Update tag UI
  document.querySelectorAll('.color-tag').forEach(tag => {
    if (tag.dataset.code === code) {
      tag.classList.toggle('active');
    }
  });

  renderCanvas();
  
  // Sync to ESP32
  sendHighlightToESP32();
}

// === Send Highlight to ESP32 ===
async function sendHighlightToESP32() {
  const { pixelMatrix, activeColors, connectionMode, colorData } = window.appState;
  if (!pixelMatrix) return;
  
  // Get RGB values for highlighted colors
  const highlightRGB = [];
  activeColors.forEach(code => {
    if (colorData[code] && colorData[code].rgb) {
      highlightRGB.push(colorData[code].rgb);
    }
  });
  
  try {
    if (connectionMode === 'ble') {
      const deviceAddress = document.getElementById('ble-device-select')?.value;
      if (!deviceAddress) return;
      
      await fetch('/api/ble/highlight', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          highlight_colors: highlightRGB,
          device_address: deviceAddress,
        }),
      });
    } else {
      // Serial mode - send highlight command
      const port = document.getElementById('serial-port-select')?.value;
      if (!port) return;
      
      await fetch('/api/serial/highlight', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          highlight_colors: highlightRGB,
          port: port,
        }),
      });
    }
  } catch (err) {
    console.error('ESP32 highlight sync failed:', err);
  }
}

// === Edit Mode Toggle ===
function toggleEditMode() {
  window.appState.editMode = !window.appState.editMode;
  const btn = document.getElementById('edit-toggle');
  if (btn) {
    btn.classList.toggle('active', window.appState.editMode);
    btn.textContent = window.appState.editMode ? t('btn.exit_edit') : t('btn.edit');
  }
}

// === Export PNG ===
async function exportPNG() {
  const { pixelMatrix, colorData, colorSummary, palettePreset, fullPalette } = window.appState;
  if (!pixelMatrix) return;

  // Build color_data map: code -> hex (include fullPalette fallback)
  const colorMap = {};
  Object.keys(colorData).forEach(code => {
    colorMap[code] = colorData[code].hex;
  });
  // Ensure all codes in pixel_matrix are covered
  pixelMatrix.forEach(row => {
    row.forEach(code => {
      if (code && !colorMap[code] && fullPalette[code]) {
        colorMap[code] = fullPalette[code].hex;
      }
    });
  });

  try {
    const response = await fetch('/api/export/png', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: window.appState.sessionId,
        pixel_matrix: pixelMatrix,
        color_data: colorMap,
        color_summary: colorSummary,
        cell_size: 20,
        show_grid: true,
        show_codes_in_cells: true,
        show_coordinates: true,
        palette_preset: palettePreset,
      }),
    });

    if (!response.ok) throw new Error('Export failed');

    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `beadcraft_pattern_${Date.now()}.png`;
    a.click();
    URL.revokeObjectURL(url);

    showToast(t('toast.png_success'));
  } catch (err) {
    showToast(t('toast.png_failed'), true);
  }
}

// === Export PDF ===
async function exportPDF() {
  const { pixelMatrix, colorSummary, sessionId, palettePreset } = window.appState;
  if (!pixelMatrix) return;

  try {
    const response = await fetch('/api/export/pdf', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: sessionId,
        pixel_matrix: pixelMatrix,
        color_summary: colorSummary,
        show_codes_in_cells: true,
        show_coordinates: true,
        palette_preset: palettePreset,
      }),
    });

    if (!response.ok) throw new Error('Export failed');

    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `beadcraft_pattern_${Date.now()}.pdf`;
    a.click();
    URL.revokeObjectURL(url);

    showToast(t('toast.pdf_success'));
  } catch (err) {
    showToast(t('toast.pdf_failed'), true);
  }
}

// === Export JSON ===
async function exportJSON() {
  const { pixelMatrix, colorSummary } = window.appState;
  if (!pixelMatrix) return;

  try {
    const response = await fetch('/api/export/json', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        pixel_matrix: pixelMatrix,
        color_summary: colorSummary,
      }),
    });

    if (!response.ok) throw new Error('Export failed');

    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `beadcraft_pattern_${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);

    showToast('JSON exported successfully');
  } catch (err) {
    showToast('JSON export failed', true);
  }
}

// === Serial Port Settings Dialog ===
window.appState.connectionMode = 'serial';  // 'ble' or 'serial' (default: serial)

function setConnectionMode(mode) {
  window.appState.connectionMode = mode;
  
  // Update button states
  document.querySelectorAll('.mode-btn').forEach(btn => {
    btn.classList.toggle('active', btn.textContent.toLowerCase().includes(mode));
  });
  
  // Toggle visibility
  document.getElementById('ble-settings').style.display = mode === 'ble' ? 'block' : 'none';
  document.getElementById('serial-settings').style.display = mode === 'serial' ? 'block' : 'none';
  
  // Auto-scan
  if (mode === 'ble') {
    refreshBLEDevices();
  } else {
    refreshSerialPorts(true);
  }
}

function showSerialSettings() {
  const { pixelMatrix } = window.appState;
  if (!pixelMatrix) {
    showToast(t('toast.generate_first'), true);
    return;
  }

  document.getElementById('serial-settings-dialog').style.display = 'flex';
  
  // Auto-scan based on mode
  if (window.appState.connectionMode === 'ble') {
    refreshBLEDevices();
  } else {
    refreshSerialPorts(true);
  }
}

function hideSerialSettings() {
  document.getElementById('serial-settings-dialog').style.display = 'none';
}

// === BLE Device Scanning ===
async function refreshBLEDevices() {
  const select = document.getElementById('ble-device-select');
  select.innerHTML = '<option value="">Scanning...</option>';

  try {
    const response = await fetch('/api/ble/devices');
    if (!response.ok) throw new Error('Failed to scan BLE');
    
    const data = await response.json();
    const devices = data.devices || [];
    
    if (devices.length === 0) {
      select.innerHTML = '<option value="">No devices found</option>';
      return;
    }
    
    select.innerHTML = '<option value="">Select device</option>';
    devices.forEach(device => {
      const opt = document.createElement('option');
      opt.value = device.address;
      opt.textContent = device.name || device.address;
      select.appendChild(opt);
    });
    
    // Auto-select first device
    if (devices.length > 0) {
      select.value = devices[0].address;
    }
  } catch (err) {
    select.innerHTML = '<option value="">Scan failed</option>';
  }
}

// === One-Click Send to ESP32 ===
async function sendToESP32Direct() {
  const { pixelMatrix, connectionMode } = window.appState;
  if (!pixelMatrix) {
    showToast(t('toast.generate_first'), true);
    return;
  }

  const bgColor = document.getElementById('serial-bg-color').value;
  const bgRgb = [
    parseInt(bgColor.slice(1, 3), 16),
    parseInt(bgColor.slice(3, 5), 16),
    parseInt(bgColor.slice(5, 7), 16),
  ];

  // Show toast
  const toast = document.getElementById('serial-toast');
  toast.textContent = connectionMode === 'ble' ? 'Connecting via Bluetooth...' : t('serial.sending');
  toast.className = 'serial-toast';
  toast.style.display = 'block';

  try {
    let result;
    
    if (connectionMode === 'ble') {
      // BLE mode
      const deviceAddress = document.getElementById('ble-device-select').value;
      if (!deviceAddress) {
        showToast('Please select a BLE device', true);
        showSerialSettings();
        toast.style.display = 'none';
        return;
      }
      
      const response = await fetch('/api/ble/send', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          pixel_matrix: pixelMatrix,
          device_address: deviceAddress,
          background_color: bgRgb,
        }),
      });
      result = await response.json();
    } else {
      // Serial mode
      const port = document.getElementById('serial-port-select').value;
      if (!port) {
        showToast(t('serial.select_port'), true);
        showSerialSettings();
        toast.style.display = 'none';
        return;
      }
      
      const baudRate = parseInt(document.getElementById('serial-baud-select').value) || 460800;
      
      const response = await fetch('/api/serial/send', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          pixel_matrix: pixelMatrix,
          port: port,
          baud_rate: baudRate,
          background_color: bgRgb,
        }),
      });
      result = await response.json();
    }

    if (result.success) {
      toast.textContent = `Sent ${result.bytes_sent} bytes in ${result.duration_ms}ms`;
      toast.className = 'serial-toast success';
      showToast(connectionMode === 'ble' ? 'Image sent via Bluetooth!' : t('serial.send_success'));
    } else {
      toast.textContent = result.message;
      toast.className = 'serial-toast error';
    }

    // Hide toast after 3s
    setTimeout(() => {
      toast.style.display = 'none';
    }, 3000);

  } catch (err) {
    toast.textContent = err.message;
    toast.className = 'serial-toast error';
    setTimeout(() => {
      toast.style.display = 'none';
    }, 3000);
  }
}

async function refreshSerialPorts(autoSelect = false) {
  const select = document.getElementById('serial-port-select');
  select.innerHTML = '<option value="">' + t('serial.scanning') + '</option>';

  try {
    const response = await fetch('/api/serial/ports');
    if (!response.ok) throw new Error('Failed to list ports');

    const data = await response.json();
    const ports = data.ports || [];

    if (ports.length === 0) {
      select.innerHTML = '<option value="">' + t('serial.no_ports') + '</option>';
      return;
    }

    select.innerHTML = '<option value="">' + t('serial.select_port') + '</option>';
    
    let esp32Port = null;
    
    ports.forEach(port => {
      const opt = document.createElement('option');
      opt.value = port.device;
      opt.textContent = port.description || port.device;
      select.appendChild(opt);
      
      // Auto-detect ESP32 port by common identifiers
      const desc = (port.description || '').toLowerCase();
      const hwid = (port.hwid || '').toLowerCase();
      if (desc.includes('esp32') || desc.includes('ch340') || desc.includes('ch341') ||
          desc.includes('cp210') || desc.includes('cp2102') || desc.includes('cp2104') ||
          desc.includes('usb-serial') || hwid.includes('esp32') || hwid.includes('ch340')) {
        if (!esp32Port) {
          esp32Port = port.device;
        }
      }
    });
    
    // Auto-select ESP32 port if found and requested
    if (autoSelect && esp32Port) {
      select.value = esp32Port;
    }

  } catch (err) {
    select.innerHTML = '<option value="">' + t('serial.scan_failed') + '</option>';
  }
}
