/* ===== Studio Editor (final, fully wired) ===== */

const canvas = document.getElementById('board') || document.getElementById('a4-canvas');
if (!canvas) console.error('Studio: canvas element #board or #a4-canvas not found');

const GRID_SIZE = 10;
const ROTATION_SNAP = 5;
const SNAP_TOLERANCE = 5;

// Selection & interaction state
let selectedElements = new Set();
let isDragging = false, isResizing = false, isRotating = false, isEditingText = false, isMarqueeSelecting = false;
let dragStartX = 0, dragStartY = 0;
let initialWidth = 0, initialHeight = 0, initialLeft = 0, initialTop = 0;
let marqueeRect = null, marqueeStart = { x: 0, y: 0 };
let hGuide, vGuide;
let profilePictureBox = null;

// Toolbar inputs (ensure these IDs exist in your HTML)
const ffSel = document.getElementById('font-family-select');   // <select>
const fsInp = document.getElementById('font-size-input');      // <input type="number">
const fcInp = document.getElementById('font-color-input');     // <input type="color">
const lineLenInp = document.getElementById('line-length-input'); // optional <input type="number">

// Undo/redo
let undoStack = [];
let redoStack = [];
const MAX_HISTORY = 50;

// Image upload (optional)
const fileInput = document.getElementById('image-upload-input');

/* ------------ Utilities ------------ */
function uuidv4(){
  return ([1e7]+-1e3+-4e3+-8e3+-1e11).replace(/[018]/g, c =>
    (c ^ crypto.getRandomValues(new Uint8Array(1))[0] & 15 >> c / 4).toString(16)
  );
}
function rgbToHex(rgb) {
  if (!rgb) return null;
  const m = rgb.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/i);
  if (!m) return null;
  const toHex = n => ('0' + (+n).toString(16)).slice(-2);
  return `#${toHex(m[1])}${toHex(m[2])}${toHex(m[3])}`;
}
function rotateElement(element, angle) {
  const base = element.style.transform.replace(/rotate\([^)]+\)/g, '').trim();
  element.style.transform = (base + ` rotate(${angle}deg)`).trim();
}
function snapToGrid(el){
  el.style.left = Math.round(el.offsetLeft / GRID_SIZE) * GRID_SIZE + 'px';
  el.style.top  = Math.round(el.offsetTop  / GRID_SIZE) * GRID_SIZE + 'px';
}

/* ------------ Handles ------------ */
function addHandles(el){
  ['tl','tr','bl','br'].forEach(p=>{
    const h = document.createElement('div'); h.className = `handle ${p}`; el.appendChild(h);
    const rh = document.createElement('div'); rh.className = `handle rot-${p}`; el.appendChild(rh);
  });
}

/* ------------ Element creation ------------ */
function createTextElement(content, styleProps = {}, x, y, width = 200, id = uuidv4()){
  const el = document.createElement('div');
  el.className = 'design-element text-box';
  el.dataset.id = id; el.dataset.type = 'text';

  Object.assign(el.style, {
    top: y + 'px',
    left: x + 'px',
    width: width + 'px',
    transform: 'rotate(0deg)'
  });

  // Apply text styles
  el.style.color = styleProps.color ?? '#000';
  el.style.fontFamily = styleProps.fontFamily ?? 'Inter, sans-serif';
  el.style.fontSize = styleProps.fontSize ?? '14px';
  el.style.fontWeight = styleProps.fontWeight ?? '400';
  if (styleProps.textAlign) el.style.textAlign = styleProps.textAlign;

  const ct = document.createElement('div');
  ct.className = 'text-content';
  ct.contentEditable = 'false';
  ct.innerHTML = content || 'Double-click to edit';
  el.appendChild(ct);

  addHandles(el); canvas.appendChild(el);
  return el;
}

function createLineElement(x, y, width = 200, color = '#0077B6', thickness = 2, id = uuidv4()){
  const el = document.createElement('div');
  el.className = 'design-element line-element';
  el.dataset.id = id; el.dataset.type = 'line';

  Object.assign(el.style, {
    top: y + 'px',
    left: x + 'px',
    width: width + 'px',
    height: thickness + 'px',
    transform: 'rotate(0deg)',
    padding: '0',
    color: color                 // << important: use color, not backgroundColor
  });

  const inner = document.createElement('div');
  inner.className = 'line-inner';
  el.appendChild(inner);

  addHandles(el); canvas.appendChild(el);
  return el;
}

function createPictureBox(x, y, imageUrl = '', id = uuidv4()){
  const el = document.createElement('div');
  el.className = 'design-element picture-box';
  el.dataset.id = id; el.dataset.type = 'image';

  Object.assign(el.style, {
    top: y + 'px',
    left: x + 'px',
    width: '80px',
    height: '80px',
    transform: 'rotate(0deg)'
  });

  if (!imageUrl) el.textContent = 'Photo';
  else el.style.backgroundImage = `url('${imageUrl}')`;

  addHandles(el); canvas.appendChild(el);
  profilePictureBox = el;
  return el;
}

/* ------------ Selection / editing ------------ */
function updateStyleControls(element){
  if (!ffSel && !fsInp && !fcInp && !lineLenInp) return;

  if (!element || selectedElements.size !== 1){
    ffSel && (ffSel.disabled = true);
    fsInp && (fsInp.disabled = true);
    fcInp && (fcInp.disabled = true);
    lineLenInp && (lineLenInp.disabled = true);
    return;
  }

  const cs = getComputedStyle(element);
  const isLine = element.classList.contains('line-element') || element.dataset.type === 'line';

  if (isLine){
    // Thickness into font-size input
    if (fsInp){ fsInp.value = parseInt(element.style.height || cs.height) || 2; fsInp.disabled = false; }
    if (fcInp){ fcInp.value = rgbToHex(cs.color) || '#0077B6'; fcInp.disabled = false; }
    ffSel && (ffSel.disabled = true);
    if (lineLenInp){ lineLenInp.value = parseInt(element.style.width || cs.width) || 200; lineLenInp.disabled = false; }
  } else {
    if (ffSel){ ffSel.value = element.style.fontFamily || cs.fontFamily; ffSel.disabled = false; }
    if (fsInp){ fsInp.value = parseInt(element.style.fontSize || cs.fontSize) || 14; fsInp.disabled = false; }
    if (fcInp){ fcInp.value = rgbToHex(element.style.color || cs.color) || '#000000'; fcInp.disabled = false; }
    lineLenInp && (lineLenInp.disabled = true);
  }
}

function selectElement(el, mode='single'){
  // stop editing everywhere
  canvas.querySelectorAll('.text-content').forEach(tc => tc.contentEditable = 'false');
  isEditingText = false;

  if (mode === 'single'){
    for (const e of selectedElements){ e.classList.remove('active'); e.style.zIndex = 5; }
    selectedElements.clear();
  }
  if (el){
    if (mode === 'remove'){ selectedElements.delete(el); el.classList.remove('active'); el.style.zIndex = 5; }
    else { selectedElements.add(el); el.classList.add('active'); el.style.zIndex = 10; }
  }
  updateStyleControls(selectedElements.size === 1 ? selectedElements.values().next().value : null);
}

function enableTextEditing(target){
  const el = target.closest('.design-element');
  if (!el) return;
  selectElement(el, 'single');
  target.contentEditable = 'true';
  isEditingText = true;
  target.focus();
  try { document.execCommand('selectAll', false, null); } catch {}
}

/* ------------ Smart guides ------------ */
function findAlignmentSnaps(draggingEl, currentLeft, currentTop){
  const snaps = { x: null, y: null };
  if (!hGuide || !vGuide) return snaps;
  hGuide.style.display = 'none'; vGuide.style.display = 'none';

  const dW = draggingEl.offsetWidth, dH = draggingEl.offsetHeight;
  const d = { L: currentLeft, C: currentLeft + dW/2, R: currentLeft + dW,
              T: currentTop,  M: currentTop  + dH/2, B: currentTop  + dH };

  const refs = [...canvas.querySelectorAll('.design-element')].filter(el => !selectedElements.has(el));
  for (const ref of refs){
    const rL = ref.offsetLeft, rT = ref.offsetTop, rW = ref.offsetWidth, rH = ref.offsetHeight;
    const r = { L:rL, C:rL+rW/2, R:rL+rW, T:rT, M:rT+rH/2, B:rT+rH };

    const xSnaps = [
      { d: d.L, r: r.L, guide: r.L }, { d: d.C, r: r.C, guide: r.C }, { d: d.R, r: r.R, guide: r.R },
      { d: d.L, r: r.R, guide: r.R }, { d: d.R, r: r.L, guide: r.L }
    ];
    for (const s of xSnaps){
      if (Math.abs(s.d - s.r) < SNAP_TOLERANCE){
        snaps.x = s.guide - (s.d - currentLeft);
        vGuide.style.left = s.guide + 'px'; vGuide.style.display = 'block';
        break;
      }
    }

    const ySnaps = [
      { d: d.T, r: r.T, guide: r.T }, { d: d.M, r: r.M, guide: r.M }, { d: d.B, r: r.B, guide: r.B },
      { d: d.T, r: r.B, guide: r.B }, { d: d.B, r: r.T, guide: r.T }
    ];
    for (const s of ySnaps){
      if (Math.abs(s.d - s.r) < SNAP_TOLERANCE){
        snaps.y = s.guide - (s.d - currentTop);
        hGuide.style.top = s.guide + 'px'; hGuide.style.display = 'block';
        break;
      }
    }

    if (snaps.x !== null && snaps.y !== null) break;
  }
  return snaps;
}

/* ------------ State (undo/redo) ------------ */
function captureState(){
  const elements = [];
  canvas.querySelectorAll('.design-element').forEach(el=>{
    const data = {
      id: el.dataset.id,
      className: el.className,
      style: el.style.cssText,
      isPictureBox: el.classList.contains('picture-box'),
      isLine: el.dataset.type === 'line',
      html: null
    };
    if (el.dataset.type === 'text'){
      data.html = el.querySelector('.text-content')?.innerHTML || '';
    } else if (el.classList.contains('picture-box')){
      data.html = el.innerHTML; // placeholder "Photo"
    }
    elements.push(data);
  });
  return elements;
}
function restoreState(state){
  if (!state) return;
  [...canvas.querySelectorAll('.design-element')].forEach(el=> el.remove());
  selectedElements.clear(); profilePictureBox = null;

  state.forEach(d=>{
    const el = document.createElement('div');
    el.className = d.className; el.dataset.id = d.id;
    el.style.cssText = d.style;
    if (d.isLine){
      const inner = document.createElement('div'); inner.className='line-inner'; el.appendChild(inner);
    } else if (d.isPictureBox){
      el.innerHTML = d.html || 'Photo'; profilePictureBox = el;
    } else if (d.html !== null){
      const ct = document.createElement('div'); ct.className='text-content';
      ct.contentEditable = 'false'; ct.innerHTML = d.html; el.appendChild(ct);
    }
    addHandles(el); canvas.appendChild(el);
  });

  updateUndoRedoButtons();
  updateStyleControls(null);
}
function saveState(){
  const cur = captureState();
  const last = undoStack.length ? undoStack[undoStack.length-1] : null;
  if (last && JSON.stringify(cur) === JSON.stringify(last)) return;
  redoStack.length = 0;
  undoStack.push(cur); if (undoStack.length > MAX_HISTORY) undoStack.shift();
  updateUndoRedoButtons();
}
function undo(){ if (undoStack.length > 1){ const cur = undoStack.pop(); redoStack.push(cur); restoreState(undoStack[undoStack.length-1]); } }
function redo(){ if (redoStack.length){ const next = redoStack.pop(); undoStack.push(next); restoreState(next); } }
function updateUndoRedoButtons(){
  document.getElementById('undo-btn')?.toggleAttribute('disabled', undoStack.length <= 1);
  document.getElementById('redo-btn')?.toggleAttribute('disabled', redoStack.length === 0);
}

/* ------------ Interaction ------------ */
document.addEventListener('mousedown', (e) => {
  if (!canvas.contains(e.target)) return;

  const canvasRect = canvas.getBoundingClientRect();
  const el = e.target.closest('.design-element');
  dragStartX = e.clientX; dragStartY = e.clientY;

  if (el){
    // handles
    if (e.target.classList.contains('handle')){
      selectElement(el, 'single');
      const classes = [...e.target.classList];
      const isRot = classes.some(c => c.startsWith('rot-'));
      if (isRot){
        isRotating = true;
      } else {
        isResizing = true;
        el.resizeHandle = classes.find(c => ['tl','tr','bl','br'].includes(c));
        initialWidth = el.offsetWidth; initialHeight = el.offsetHeight;
        initialLeft = el.offsetLeft;   initialTop = el.offsetTop;
      }
      e.preventDefault(); return;
    }

    // text content (allow dblclick to edit)
    if (e.target.classList.contains('text-content')){
      if (!e.ctrlKey && !e.metaKey && !selectedElements.has(el)) selectElement(el, 'single');
      return;
    }

    // selection
    if (e.ctrlKey || e.metaKey) selectElement(el, selectedElements.has(el) ? 'remove' : 'add');
    else if (!selectedElements.has(el)) selectElement(el, 'single');

    // drag
    isDragging = true;
    selectedElements.forEach(node=>{
      node.dataset.initialLeft = node.offsetLeft;
      node.dataset.initialTop  = node.offsetTop;
    });
    el.style.cursor = 'grabbing';
    e.preventDefault();
    return;
  }

  // marquee on canvas background
  if (e.target === canvas){
    if (!e.ctrlKey && !e.metaKey) selectElement(null);
    isMarqueeSelecting = true;
    marqueeStart.x = dragStartX - canvasRect.left;
    marqueeStart.y = dragStartY - canvasRect.top;
    if (!marqueeRect){ marqueeRect = document.createElement('div'); marqueeRect.id = 'marquee-box'; canvas.appendChild(marqueeRect); }
    Object.assign(marqueeRect.style, { display:'block', left:marqueeStart.x+'px', top:marqueeStart.y+'px', width:'0px', height:'0px' });
    e.preventDefault();
  }
});

document.addEventListener('mousemove', (e) => {
  const canvasRect = canvas.getBoundingClientRect();
  const mx = e.clientX, my = e.clientY;

  // marquee
  if (isMarqueeSelecting){
    const cx = mx - canvasRect.left, cy = my - canvasRect.top;
    const left = Math.min(marqueeStart.x, cx);
    const top  = Math.min(marqueeStart.y, cy);
    const w = Math.abs(cx - marqueeStart.x), h = Math.abs(cy - marqueeStart.y);
    Object.assign(marqueeRect.style, { left:left+'px', top:top+'px', width:w+'px', height:h+'px' });
    return;
  }

  // clear guides when not dragging
  if (!isDragging){ if (hGuide) hGuide.style.display='none'; if (vGuide) vGuide.style.display='none'; }

  // resizing (single)
  if (isResizing && selectedElements.size === 1){
    const el = selectedElements.values().next().value;
    const newX = mx - canvasRect.left, newY = my - canvasRect.top;

    let newW, newH, newL = initialLeft, newT = initialTop;
    const handle = el.resizeHandle;
    switch (handle){
      case 'tl': newW = initialWidth + (initialLeft - newX); newH = initialHeight + (initialTop - newY); newL = newX; newT = newY; break;
      case 'tr': newW = (newX - initialLeft);                 newH = initialHeight + (initialTop - newY);                 newT = newY; break;
      case 'bl': newW = initialWidth + (initialLeft - newX);  newH = (newY - initialTop);                newL = newX;                break;
      case 'br': newW = (newX - initialLeft);                 newH = (newY - initialTop);                                                    break;
    }

    if (e.shiftKey){
      const ratio = initialWidth / Math.max(initialHeight, 1);
      const dx = mx - dragStartX, dy = my - dragStartY;
      let delta = Math.abs(dx) > Math.abs(dy) ? dx : dy;
      if (handle === 'tr') delta = Math.abs(dx) > Math.abs(dy) ? dx : -dy;
      if (handle === 'bl') delta = Math.abs(dx) > Math.abs(dy) ? -dx : dy;

      let pW = Math.max(initialWidth + delta, 10);
      let pH = Math.max(initialHeight + (delta / ratio), 10);
      const dW = pW - initialWidth, dH = pH - initialHeight;
      newW = pW; newH = pH;
      if (handle.includes('t')) newT = initialTop - dH;
      if (handle.includes('l')) newL = initialLeft - dW;
    }

    const isLine = el.dataset.type === 'line';
    if (newW > 10){ el.style.width = newW + 'px'; el.style.left = newL + 'px'; }
    if (!isLine && newH > 10){ el.style.height = newH + 'px'; el.style.top = newT + 'px'; }
    else if (isLine){ el.style.top = newT + 'px'; }
    if (!isLine && !e.shiftKey) el.style.height = 'auto';
    return;
  }

  // dragging (single or multi)
  if (isDragging && selectedElements.size > 0){
    const dx = mx - dragStartX, dy = my - dragStartY;
    selectedElements.forEach(el=>{
      const baseL = parseFloat(el.dataset.initialLeft);
      const baseT = parseFloat(el.dataset.initialTop);
      let newL = baseL + dx, newT = baseT + dy;

      if (selectedElements.size === 1){
        const snaps = findAlignmentSnaps(el, newL, newT);
        if (snaps.x !== null) newL = snaps.x;
        if (snaps.y !== null) newT = snaps.y;
      }

      el.style.left = newL + 'px'; el.style.top = newT + 'px';
    });
    return;
  }

  // rotation (single)
  if (isRotating && selectedElements.size === 1){
    const el = selectedElements.values().next().value;
    const r = el.getBoundingClientRect();
    const cx = r.left + r.width/2, cy = r.top + r.height/2;
    const ang = Math.atan2(my - cy, mx - cx) * 180/Math.PI + 90;
    let newAng = (ang + 360) % 360;
    if (e.shiftKey) newAng = Math.round(newAng / ROTATION_SNAP) * ROTATION_SNAP;
    rotateElement(el, newAng);
  }
});

document.addEventListener('mouseup', (e) => {
  // finish marquee
  if (isMarqueeSelecting){
    isMarqueeSelecting = false;
    const m = marqueeRect.getBoundingClientRect();
    marqueeRect.style.display = 'none';

    if (!e.ctrlKey && !e.metaKey) selectElement(null, 'single');
    canvas.querySelectorAll('.design-element').forEach(el=>{
      const r = el.getBoundingClientRect();
      const intersects = !(r.right < m.left || r.left > m.right || r.bottom < m.top || r.top > m.bottom);
      if (intersects){
        if (e.ctrlKey || e.metaKey) selectElement(el, selectedElements.has(el) ? 'remove' : 'add');
        else selectElement(el, 'add');
      }
    });
    saveState();
    return;
  }

  if (isDragging || isResizing || isRotating){
    selectedElements.forEach(el=>{
      snapToGrid(el);
      el.style.cursor = 'grab';
      el.removeAttribute('data-initial-left'); el.removeAttribute('data-initial-top');
    });
    saveState();
  }

  isDragging = isResizing = isRotating = false;
  if (hGuide) hGuide.style.display = 'none';
  if (vGuide) vGuide.style.display = 'none';
});

/* dblclick to edit text */
document.addEventListener('dblclick', (e)=>{
  if (e.target.classList.contains('text-content')){
    enableTextEditing(e.target);
    e.preventDefault();
  }
});

/* blur to stop editing */
document.addEventListener('focusout', (e)=>{
  if (e.target.classList.contains('text-content')){
    e.target.contentEditable = 'false';
    isEditingText = false;
    const parent = e.target.closest('.design-element');
    if (parent){
      parent.style.cursor = 'grab';
      if (parent.dataset.type === 'text') parent.style.height = 'auto';
    }
    saveState();
    setTimeout(()=>{ if (document.activeElement === document.body) selectElement(null); }, 0);
  }
}, true);

/* keyboard: delete + undo/redo */
document.addEventListener('keydown', (e)=>{
  if ((e.key === 'Delete' || e.key === 'Backspace') && !isEditingText){
    if (selectedElements.size){
      selectedElements.forEach(el=> el.remove());
      selectedElements.clear(); updateStyleControls(null); saveState(); e.preventDefault();
    }
  }
  if (e.metaKey || e.ctrlKey){
    if (e.key.toLowerCase() === 'z'){ if (e.shiftKey) redo(); else undo(); e.preventDefault(); }
    else if (e.key.toLowerCase() === 'y'){ redo(); e.preventDefault(); }
  }
});

/* ------------ Image upload hook ------------ */
function triggerImageUpload(){ if (profilePictureBox && fileInput){ fileInput.value = null; fileInput.click(); } }
fileInput?.addEventListener('change', (e)=>{
  const f = e.target.files?.[0]; if (!f || !f.type.startsWith('image/') || !profilePictureBox) return;
  const reader = new FileReader();
  reader.onload = ev => { profilePictureBox.style.backgroundImage = `url('${ev.target.result}')`; profilePictureBox.textContent = ''; saveState(); };
  reader.readAsDataURL(f);
});

/* ------------ Header + guides + starter layout ------------ */
function ensureHeader(){
  let header = canvas.querySelector('.header-bg');
  if (!header){ header = document.createElement('div'); header.className = 'header-bg'; canvas.appendChild(header); }
  header.style.zIndex = 0;
}
function initializeGuides(){
  hGuide = document.createElement('div'); hGuide.className = 'guide-line h'; canvas.appendChild(hGuide);
  vGuide = document.createElement('div'); vGuide.className = 'guide-line v'; canvas.appendChild(vGuide);
}
function initializeResumeLayout(){
  createTextElement('JANE DOE', { color:'white', fontSize:'36px', fontWeight:'700' }, 40, 30, 300);
  createTextElement('Senior UX/UI Designer', { color:'white', fontSize:'18px', fontWeight:'300' }, 40, 75, 300);
  createTextElement('jane.doe@example.com', { color:'white', fontSize:'14px', textAlign:'right' }, 550, 35, 200);
  createTextElement('(555) 123-4567', { color:'white', fontSize:'14px', textAlign:'right' }, 550, 55, 200);
  createTextElement('linkedin.com/in/janedoe', { color:'white', fontSize:'14px', textAlign:'right' }, 550, 75, 200);

  profilePictureBox = createPictureBox(80, 150);

  createTextElement('SKILLS', { color:'#0077B6', fontSize:'20px', fontWeight:'600' }, 40, 260, 200);
  createLineElement(40, 290, 200);
  createTextElement('Figma, Sketch, Adobe XD', { fontSize:'14px' }, 40, 305, 200);
  createTextElement('User Research, Prototyping', { fontSize:'14px' }, 40, 330, 200);
  createTextElement('HTML/CSS, JavaScript', { fontSize:'14px' }, 40, 355, 200);

  createTextElement('EDUCATION', { color:'#0077B6', fontSize:'20px', fontWeight:'600' }, 40, 410, 200);
  createLineElement(40, 440, 200);
  createTextElement('Master of Science in HCI', { fontSize:'16px', fontWeight:'600' }, 40, 455, 200);
  createTextElement('University of Washington | 2017', { fontSize:'14px', color:'#555' }, 40, 480, 200);
  createTextElement('B.A. Graphic Design', { fontSize:'16px', fontWeight:'600' }, 40, 520, 200);
  createTextElement('Art Center College of Design | 2015', { fontSize:'14px', color:'#555' }, 40, 545, 200);

  createTextElement('PROFESSIONAL SUMMARY', { color:'#0077B6', fontSize:'20px', fontWeight:'600' }, 300, 160, 450);
  createLineElement(300, 190, 450);
  createTextElement('Highly motivated Senior UX/UI Designer with 7+ years of experience in leading product design cycles from concept to launch. Proven ability to translate complex user needs into intuitive and beautiful digital experiences, resulting in a 25% increase in user engagement across key product lines. Expertise in SaaS platforms and enterprise solutions.', { fontSize:'14px', color:'#555' }, 300, 205, 450);

  createTextElement('EXPERIENCE', { color:'#0077B6', fontSize:'20px', fontWeight:'600' }, 300, 360, 450);
  createLineElement(300, 390, 450);

  createTextElement('Lead Product Designer', { fontSize:'16px', fontWeight:'600' }, 300, 405, 450);
  createTextElement('Tech Innovators Inc. | 2020 – Present', { fontSize:'14px', color:'#555' }, 300, 425, 450);
  createTextElement('• Led the design of a flagship enterprise analytics dashboard, improving data comprehension speed by 40%.', { fontSize:'14px', color:'#333' }, 300, 455, 450);
  createTextElement('• Mentored three junior designers and implemented a standardized design system (Figma) utilized across 5 product teams.', { fontSize:'14px', color:'#333' }, 300, 475, 450);
  createTextElement('• Conducted over 50 usability tests and competitive analyses to inform product strategy.', { fontSize:'14px', color:'#333' }, 300, 495, 450);

  createTextElement('UX/UI Designer', { fontSize:'16px', fontWeight:'600' }, 300, 540, 450);
  createTextElement('Creative Solutions Agency | 2017 – 2020', { fontSize:'14px', color:'#555' }, 300, 560, 450);
  createTextElement('• Designed and launched three major client websites and mobile applications.', { fontSize:'14px', color:'#333' }, 300, 590, 450);
  createTextElement('• Collaborated closely with front-end developers to ensure technical feasibility and pixel-perfect implementation.', { fontSize:'14px', color:'#333' }, 300, 610, 450);

  saveState();
}

/* ------------ Toolbar wiring (optionally add buttons) ------------ */
function wireToolbar(){
  document.getElementById('btn-add-text')?.addEventListener('click', ()=>{
    const el = createTextElement('New Text Box', { fontSize:'16px', fontWeight:'bold' }, 350, 500, 200);
    selectElement(el, 'single'); saveState();
  });
  document.getElementById('btn-add-line')?.addEventListener('click', ()=>{
    const el = createLineElement(350, 550, 300);
    selectElement(el, 'single'); saveState();
  });
  document.getElementById('btn-add-image')?.addEventListener('click', ()=>{
    if (!profilePictureBox) profilePictureBox = createPictureBox(80, 150);
    triggerImageUpload();
  });

  document.getElementById('undo-btn')?.addEventListener('click', ()=> undo());
  document.getElementById('redo-btn')?.addEventListener('click', ()=> redo());
}

/* ------------ Style controls wiring ------------ */
function wireStyleControls(){
  // Font family (text only)
  ffSel?.addEventListener('change', e=>{
    if (selectedElements.size !== 1) return;
    const el = selectedElements.values().next().value;
    if (el.dataset.type === 'line') return;
    el.querySelector('.text-content').style.fontFamily = e.target.value;
    saveState();
  });

  // Font size:
  //  - text: font-size (px)
  //  - line: thickness (height in px)
  fsInp?.addEventListener('change', e=>{
    const val = parseInt(e.target.value, 10);
    if (Number.isNaN(val) || selectedElements.size !== 1) return;
    const el = selectedElements.values().next().value;

    if (el.dataset.type === 'line'){
      el.style.height = Math.max(val, 1) + 'px';     // thickness
    } else {
      el.querySelector('.text-content').style.fontSize = Math.max(val, 1) + 'px';   // text size
      el.style.height = 'auto';
    }
    saveState();
  });

  // Color:
  //  - text: color
  //  - line: element color (drives .line-inner via currentColor)
  fcInp?.addEventListener('change', e=>{
    if (selectedElements.size !== 1) return;
    const el = selectedElements.values().next().value;
    el.querySelector('.text-content').style.color = e.target.value;
    saveState();
  });

  // Optional: line length (width)
  lineLenInp?.addEventListener('change', e=>{
    const val = parseInt(e.target.value, 10);
    if (Number.isNaN(val) || selectedElements.size !== 1) return;
    const el = selectedElements.values().next().value;
    if (el.dataset.type !== 'line') return;
    el.style.width = Math.max(val, 10) + 'px';
    saveState();
  });
}

/* ------------ Start ------------ */
window.addEventListener('DOMContentLoaded', ()=>{
  ensureHeader();
  initializeGuides();
  initializeResumeLayout();
  wireToolbar();
  wireStyleControls();    // << attaches input listeners
});
