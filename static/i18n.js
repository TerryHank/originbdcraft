// === BeadCraft Internationalization ===

const I18N = {
  zh: {
    // Header
    'header.api_docs': 'API 文档',

    // Upload
    'upload.drop_hint': '拖拽图片到这里，或点击上传',
    'upload.format_hint': 'JPG, PNG, GIF, WEBP (最大 20MB)',

    // Settings - Palette
    'settings.palette_preset': '色板预设',

    // Settings - Grid
    'settings.board_size': '拼豆板尺寸',
    'settings.fixed_grid': '固定网格',
    'settings.pixel_block': '像素块大小',
    'settings.pixel_block_label': '像素块大小:',
    'grid.small': '颗 (小)',
    'grid.1board': '颗 (1块板)',
    'grid.default': '颗',
    'grid.2x2': '颗 (2x2板)',
    'grid.3x3': '颗 (3x3板)',

    // Settings - Color
    'settings.color_controls': '颜色控制',
    'settings.max_colors': '最大颜色数:',
    'settings.max_colors_hint': '0 = 不限 (自动)。拖动滑块限制使用的颜色数量。',
    'settings.merge_threshold': '颜色合并阈值:',
    'settings.merge_hint': '合并相似颜色以减少总数。值越大合并越多。',

    // Settings - Adjustments
    'settings.image_adjustments': '图像调整',
    'settings.contrast': '对比度:',
    'settings.saturation': '饱和度:',
    'settings.sharpness': '锐度:',
    'settings.adjust_hint': '0 = 自动检测。向左减弱，向右增强。',

    // Settings - Background
    'settings.bg_removal': '背景去除',
    'settings.auto_remove_bg': '自动去除背景',
    'settings.bg_hint': '检测边缘主色并以透明色填充。',

    // Settings - Dithering
    'settings.dithering': '抖动处理',
    'settings.enable_dithering': '启用 Floyd-Steinberg 抖动',
    'settings.dithering_hint': '产生更平滑的颜色过渡，但处理时间更长',

    // Buttons
    'btn.generate': '生成图案',
    'btn.edit': '编辑',
    'btn.exit_edit': '退出编辑',
    'btn.export_png': '导出 PNG',
    'btn.export_pdf': '导出 PDF',

    // Result
    'result.empty': '上传图片并生成拼豆图案',
    'result.colors_used': '使用的颜色',
    'result.colors_total': '{colors} 种颜色, 共 {beads} 颗珠子',

    // Examples
    'examples.title': '示例图片',

    // Toast messages
    'toast.upload_type_error': '请上传图片文件 (JPG, PNG, GIF, WEBP)',
    'toast.upload_size_error': '文件大小超过 20MB 限制',
    'toast.upload_first': '请先上传图片',
    'toast.processing': '处理中...',
    'toast.pattern_result': '图案: {w}x{h}, {c} 种颜色',
    'toast.timeout': '处理超时，请尝试降低分辨率。',
    'toast.update_failed': '更新单元格失败',
    'toast.png_success': 'PNG 导出成功',
    'toast.png_failed': 'PNG 导出失败',
    'toast.pdf_success': 'PDF 导出成功',
    'toast.pdf_failed': 'PDF 导出失败',
    'toast.example_loaded': '示例图片已加载',
    'toast.example_load_error': '加载示例图片失败',

    // Slider values
    'value.auto': '自动',
    'value.off': '关闭',

    // Serial port
    'btn.send_esp32': '发送到 ESP32',
    'serial.title': '发送到 ESP32',
    'serial.port': '串口:',
    'serial.baud_rate': '波特率:',
    'serial.bg_color': '背景色 (透明区域):',
    'serial.scanning': '扫描中...',
    'serial.no_ports': '未找到串口',
    'serial.scan_failed': '扫描失败',
    'serial.refresh': '刷新',
    'serial.send': '发送',
    'serial.sending': '正在发送...',
    'serial.success': '发送成功! {bytes} 字节, 耗时 {ms}ms',
    'serial.error': '错误: {msg}',
    'serial.select_port': '请选择串口',
    'serial.send_success': '已发送到 ESP32',
    'serial.esp32_log': 'ESP32 日志:',
    'serial.clear': '清除',
    'btn.cancel': '取消',
    'toast.generate_first': '请先生成图案',
  },

  en: {
    // Header
    'header.api_docs': 'API Docs',

    // Upload
    'upload.drop_hint': 'Drop image here or click to upload',
    'upload.format_hint': 'JPG, PNG, GIF, WEBP (max 20MB)',

    // Settings - Palette
    'settings.palette_preset': 'Palette Preset',

    // Settings - Grid
    'settings.board_size': 'Bead Board Size',
    'settings.fixed_grid': 'Fixed Grid',
    'settings.pixel_block': 'Pixel Block Size',
    'settings.pixel_block_label': 'Pixel block size:',
    'grid.small': 'pegs (small)',
    'grid.1board': 'pegs (1 board)',
    'grid.default': 'pegs',
    'grid.2x2': 'pegs (2x2 boards)',
    'grid.3x3': 'pegs (3x3 boards)',

    // Settings - Color
    'settings.color_controls': 'Color Controls',
    'settings.max_colors': 'Max colors:',
    'settings.max_colors_hint': '0 = unlimited (auto). Drag to limit the number of colors used.',
    'settings.merge_threshold': 'Color merge threshold:',
    'settings.merge_hint': 'Merge similar colors to reduce total count. Higher = more merging.',

    // Settings - Adjustments
    'settings.image_adjustments': 'Image Adjustments',
    'settings.contrast': 'Contrast:',
    'settings.saturation': 'Saturation:',
    'settings.sharpness': 'Sharpness:',
    'settings.adjust_hint': '0 = auto-detect. Drag left to reduce, right to boost.',

    // Settings - Background
    'settings.bg_removal': 'Background Removal',
    'settings.auto_remove_bg': 'Auto remove background',
    'settings.bg_hint': 'Detects the dominant border color and flood-fills it as transparent.',

    // Settings - Dithering
    'settings.dithering': 'Dithering',
    'settings.enable_dithering': 'Enable Floyd-Steinberg dithering',
    'settings.dithering_hint': 'Produces smoother color transitions but takes longer',

    // Buttons
    'btn.generate': 'Generate Pattern',
    'btn.edit': 'Edit',
    'btn.exit_edit': 'Exit Edit',
    'btn.export_png': 'Export PNG',
    'btn.export_pdf': 'Export PDF',

    // Result
    'result.empty': 'Upload an image and generate a pattern',
    'result.colors_used': 'Colors Used',
    'result.colors_total': '{colors} colors, {beads} beads total',

    // Examples
    'examples.title': 'Example Images',

    // Toast messages
    'toast.upload_type_error': 'Please upload an image file (JPG, PNG, GIF, WEBP)',
    'toast.upload_size_error': 'File size exceeds 20MB limit',
    'toast.upload_first': 'Please upload an image first',
    'toast.processing': 'Processing...',
    'toast.pattern_result': 'Pattern: {w}x{h}, {c} colors',
    'toast.timeout': 'Processing timeout. Try reducing resolution.',
    'toast.update_failed': 'Failed to update cell',
    'toast.png_success': 'PNG exported successfully',
    'toast.png_failed': 'PNG export failed',
    'toast.pdf_success': 'PDF exported successfully',
    'toast.pdf_failed': 'PDF export failed',
    'toast.example_loaded': 'Example image loaded',
    'toast.example_load_error': 'Failed to load example image',

    // Slider values
    'value.auto': 'Auto',
    'value.off': 'Off',

    // Serial port
    'btn.send_esp32': 'Send to ESP32',
    'serial.title': 'Send to ESP32',
    'serial.port': 'Serial Port:',
    'serial.baud_rate': 'Baud Rate:',
    'serial.bg_color': 'Background Color (transparent areas):',
    'serial.scanning': 'Scanning...',
    'serial.no_ports': 'No ports found',
    'serial.scan_failed': 'Scan failed',
    'serial.refresh': 'Refresh',
    'serial.send': 'Send',
    'serial.sending': 'Sending...',
    'serial.success': 'Success! {bytes} bytes sent in {ms}ms',
    'serial.error': 'Error: {msg}',
    'serial.select_port': 'Please select a port',
    'serial.send_success': 'Sent to ESP32',
    'serial.esp32_log': 'ESP32 Log:',
    'serial.clear': 'Clear',
    'btn.cancel': 'Cancel',
    'toast.generate_first': 'Please generate a pattern first',
  }
};

// Current language (default: zh)
let currentLang = localStorage.getItem('beadcraft_lang') || 'zh';

// Get translated string, with optional template variables
function t(key, vars) {
  const str = (I18N[currentLang] && I18N[currentLang][key]) || (I18N['en'] && I18N['en'][key]) || key;
  if (!vars) return str;
  return str.replace(/\{(\w+)\}/g, (_, k) => vars[k] !== undefined ? vars[k] : `{${k}}`);
}

// Apply translations to all elements with data-i18n attribute
function applyTranslations() {
  document.querySelectorAll('[data-i18n]').forEach(el => {
    const key = el.getAttribute('data-i18n');
    const translated = t(key);
    // For input elements, set placeholder; for others, set textContent
    if (el.tagName === 'INPUT' && el.type !== 'checkbox' && el.type !== 'radio') {
      el.placeholder = translated;
    } else {
      el.textContent = translated;
    }
  });

  // Update grid size options
  updateGridOptions();

  // Update dynamic slider labels
  updateSliderLabels();
}

// Update grid select options with translated text
function updateGridOptions() {
  const select = document.getElementById('grid-size-select');
  if (!select) return;
  const options = select.options;
  const gridTexts = {
    '15x15': `15 x 15 ${t('grid.small')}`,
    '29x29': `29 x 29 ${t('grid.1board')}`,
    '32x32': `32 x 32 ${t('grid.default')}`,
    '48x48': `48 x 48 ${t('grid.default')}`,
    '58x58': `58 x 58 ${t('grid.2x2')}`,
    '64x64': `64 x 64 ${t('grid.default')}`,
    '87x87': `87 x 87 ${t('grid.3x3')}`,
    '96x96': `96 x 96 ${t('grid.default')}`,
  };
  for (let i = 0; i < options.length; i++) {
    const val = options[i].value;
    if (gridTexts[val]) {
      options[i].textContent = gridTexts[val];
    }
  }
}

// Re-apply slider value labels after language switch
function updateSliderLabels() {
  const maxSlider = document.getElementById('max-colors-slider');
  if (maxSlider) {
    const v = parseInt(maxSlider.value);
    document.getElementById('max-colors-value').textContent = v === 0 ? t('value.auto') : v;
  }

  const simSlider = document.getElementById('similarity-slider');
  if (simSlider) {
    const v = parseInt(simSlider.value);
    document.getElementById('similarity-value').textContent = v === 0 ? t('value.off') : v;
  }

  ['contrast', 'saturation', 'sharpness'].forEach(name => {
    const slider = document.getElementById(`${name}-slider`);
    const display = document.getElementById(`${name}-value`);
    if (slider && display) {
      const v = parseInt(slider.value);
      display.textContent = v === 0 ? t('value.auto') : (v > 0 ? '+' + v : v);
    }
  });
}

// Switch language
function setLanguage(lang) {
  currentLang = lang;
  localStorage.setItem('beadcraft_lang', lang);
  applyTranslations();

  // Update language switcher button states
  document.querySelectorAll('.lang-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.lang === lang);
  });

  // Re-render color panel if data exists
  if (window.appState && window.appState.colorSummary && window.appState.colorSummary.length > 0) {
    if (typeof renderColorPanel === 'function') renderColorPanel();
  }

  // Update generate button text (if not processing)
  const genBtn = document.getElementById('generate-btn');
  if (genBtn && !genBtn.disabled) {
    genBtn.textContent = t('btn.generate');
  }

  // Update edit toggle button
  const editBtn = document.getElementById('edit-toggle');
  if (editBtn) {
    editBtn.textContent = window.appState && window.appState.editMode ? t('btn.exit_edit') : t('btn.edit');
  }
}
