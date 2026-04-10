/* ── PPT Agent SPA ── */
'use strict';

// ─────────────────────────────────────────────────────────────────
// API 层
// ─────────────────────────────────────────────────────────────────
const api = {
  async _fetch(method, path, body) {
    const opts = { method, headers: { 'Content-Type': 'application/json' } };
    if (body !== undefined) opts.body = JSON.stringify(body);
    const res  = await fetch(path, opts);
    const json = await res.json();
    if (json.success === false) throw new Error(json.error || `HTTP ${res.status}`);
    return json.data;
  },

  listProjects:    ()         => api._fetch('GET',   '/projects'),
  getProject:      (id)       => api._fetch('GET',   `/projects/${id}`),
  createProject:   (body)     => api._fetch('POST',  '/projects', body),
  updateBrief:     (id, body) => api._fetch('PATCH', `/projects/${id}/brief`, body),
  confirmBrief:    (id)       => api._fetch('POST',  `/projects/${id}/confirm-brief`),
  generateOutline: (id)       => api._fetch('POST',  `/projects/${id}/outline/generate`),
  confirmOutline:  (id)       => api._fetch('POST',  `/projects/${id}/outline/confirm`),
  listSlides:      (id)       => api._fetch('GET',   `/projects/${id}/slides`),
  triggerReview:   (id)       => api._fetch('POST',  `/projects/${id}/review`),
  exportPDF:       (id)       => api._fetch('POST',  `/projects/${id}/export`, { export_type: 'pdf' }),
};

// ─────────────────────────────────────────────────────────────────
// 路由
// ─────────────────────────────────────────────────────────────────
let _pollTimer = null;

function clearPoll() {
  if (_pollTimer) { clearInterval(_pollTimer); _pollTimer = null; }
}

function navigate(hash) {
  clearPoll();
  window.location.hash = hash;
}

function getRoute(hash) {
  const path = (hash || '').replace(/^#/, '') || '/';
  if (path === '/')    return { view: 'list',   id: null };
  if (path === '/new') return { view: 'new',    id: null };
  const m = path.match(/^\/project\/([^/]+)$/);
  if (m)               return { view: 'detail', id: m[1] };
  return { view: 'list', id: null };
}

window.addEventListener('hashchange', () => {
  clearPoll();
  dispatch(getRoute(window.location.hash));
});

window.addEventListener('DOMContentLoaded', () => {
  dispatch(getRoute(window.location.hash));
});

function dispatch({ view, id }) {
  if (view === 'list')   renderProjectList();
  else if (view === 'new')    renderNewProject();
  else if (view === 'detail') renderProjectDetail(id);
}

// ─────────────────────────────────────────────────────────────────
// 辅助
// ─────────────────────────────────────────────────────────────────
const $app = () => document.getElementById('app');

function mountTemplate(id) {
  const frag = document.getElementById(id).content.cloneNode(true);
  $app().innerHTML = '';
  $app().appendChild(frag);
}

function showError(msg) {
  const el = document.createElement('div');
  el.className = 'error-toast';
  el.textContent = msg;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 4000);
}

// 状态 → 显示文字
const STATUS_LABEL = {
  INIT:                '初始化',
  INTAKE_IN_PROGRESS:  '填写中',
  INTAKE_CONFIRMED:    'Brief 已确认',
  REFERENCE_SELECTION: '参考案例选择',
  ASSET_GENERATING:    '资产生成中',
  OUTLINE_READY:       '大纲已生成',
  SLIDE_PLANNING:      '排版中',
  RENDERING:           '渲染中',
  REVIEWING:           '审查中',
  READY_FOR_EXPORT:    '待导出',
  EXPORTED:            '已导出',
  FAILED:              '失败',
};

// 状态 → Badge CSS class
function statusClass(s) {
  if (!s) return 's-default';
  if (['INIT', 'INTAKE_IN_PROGRESS', 'INTAKE_CONFIRMED'].includes(s)) return 's-intake';
  if (s === 'OUTLINE_READY')  return 's-outline';
  if (['SLIDE_PLANNING', 'RENDERING', 'REVIEWING', 'ASSET_GENERATING', 'REFERENCE_SELECTION'].includes(s)) return 's-rendering';
  if (s === 'READY_FOR_EXPORT') return 's-ready';
  if (s === 'EXPORTED')  return 's-exported';
  if (s === 'FAILED')    return 's-failed';
  return 's-default';
}

// 状态 → Stepper 当前步骤（1-5，0 = 未开始）
const STATUS_STEP = {
  INIT:                1,
  INTAKE_IN_PROGRESS:  1,
  INTAKE_CONFIRMED:    1,
  REFERENCE_SELECTION: 1,
  ASSET_GENERATING:    1,
  OUTLINE_READY:       2,
  SLIDE_PLANNING:      3,
  RENDERING:           3,
  REVIEWING:           4,
  READY_FOR_EXPORT:    5,
  EXPORTED:            5,
  FAILED:              0,
};

// 终态（轮询停止）
const TERMINAL = new Set([
  'INTAKE_CONFIRMED', 'OUTLINE_READY', 'READY_FOR_EXPORT', 'EXPORTED', 'FAILED',
]);

// ─────────────────────────────────────────────────────────────────
// View 1：项目列表
// ─────────────────────────────────────────────────────────────────
async function renderProjectList() {
  mountTemplate('tpl-project-list');

  let projects;
  try { projects = await api.listProjects(); }
  catch (e) { showError(e.message); return; }

  const grid = document.getElementById('project-grid');
  const hint = document.getElementById('empty-hint');

  if (!projects || !projects.length) {
    hint.style.display = 'block';
    return;
  }

  for (const p of projects) {
    const card = document.createElement('div');
    card.className = 'project-card';
    const label = STATUS_LABEL[p.status] || p.status || '—';
    const cls   = statusClass(p.status);
    card.innerHTML = `
      <div class="project-card-name">${esc(p.name)}</div>
      <span class="status-badge ${cls}">${esc(label)}</span>
      <div class="project-card-meta">${(p.created_at || '').slice(0, 10)}</div>
    `;
    card.onclick = () => navigate(`#/project/${p.id}`);
    grid.appendChild(card);
  }
}

// ─────────────────────────────────────────────────────────────────
// View 2：新建项目（Brief 表单）
// ─────────────────────────────────────────────────────────────────
function renderNewProject() {
  mountTemplate('tpl-new-project');

  document.getElementById('brief-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const form = e.target;
    const btn  = document.getElementById('submit-btn');
    btn.disabled = true;
    btn.textContent = '创建中…';

    const data   = Object.fromEntries(new FormData(form));
    const styles = [...form.querySelectorAll('[name=style]:checked')].map(cb => cb.value);

    // 构建 raw_text 传给 Intake Agent
    const lines = [
      data.building_type        && `建筑类型：${data.building_type}`,
      data.client_name          && `委托方：${data.client_name}`,
      data.city                 && `城市：${data.city}`,
      data.site_address         && `场地地址：${data.site_address}`,
      data.gross_floor_area     && `总建筑面积：${data.gross_floor_area}㎡`,
      data.site_area            && `用地面积：${data.site_area}㎡`,
      styles.length             && `风格偏好：${styles.join('、')}`,
      data.special_requirements && `特殊要求：${data.special_requirements}`,
    ].filter(Boolean);

    try {
      // 1. 创建项目
      const project = await api.createProject({ name: data.name });

      // 2. 通过 Intake Agent 填写 Brief
      const briefResult = await api.updateBrief(project.id, { raw_text: lines.join('\n') });

      // 3. 确认 Brief（如果已完整）
      if (briefResult?.brief?.is_complete) {
        await api.confirmBrief(project.id);
      }

      navigate(`#/project/${project.id}`);
    } catch (err) {
      showError(err.message);
      btn.disabled    = false;
      btn.textContent = '创建并开始 →';
    }
  });
}

// ─────────────────────────────────────────────────────────────────
// View 3：项目详情
// ─────────────────────────────────────────────────────────────────
async function renderProjectDetail(id) {
  mountTemplate('tpl-project-detail');

  let project;
  try { project = await api.getProject(id); }
  catch (e) { showError(e.message); return; }

  applyDetail(project);

  // 若非终态，开始轮询
  if (!TERMINAL.has(project.status)) {
    _pollTimer = setInterval(async () => {
      try {
        project = await api.getProject(id);
        applyDetail(project);
        if (TERMINAL.has(project.status)) clearPoll();
      } catch { clearPoll(); }
    }, 3000);
  }
}

function applyDetail(project) {
  // 标题 + badge
  const el = document.getElementById('detail-title');
  if (el) el.textContent = project.name;

  const badge = document.getElementById('detail-status');
  if (badge) {
    badge.textContent = STATUS_LABEL[project.status] || project.status || '';
    badge.className   = `status-badge ${statusClass(project.status)}`;
  }

  // Stepper
  const step = STATUS_STEP[project.status] ?? 0;
  document.querySelectorAll('.step').forEach(el => {
    const n = parseInt(el.dataset.step, 10);
    el.classList.toggle('done',   n < step);
    el.classList.toggle('active', n === step);
  });
  document.querySelectorAll('.step-line').forEach((el, i) => {
    el.classList.toggle('done', i + 1 < step);
  });

  // Action bar
  buildActionBar(project);

  // 幻灯片（渲染完成后）
  if (['REVIEWING', 'READY_FOR_EXPORT', 'EXPORTED'].includes(project.status)) {
    loadSlides(project.id);
  }
}

function buildActionBar(project) {
  const bar = document.getElementById('action-bar');
  if (!bar) return;
  bar.innerHTML = '';

  const s = project.status;

  // 处理中：转圈 + 文字
  if (s && !TERMINAL.has(s) && s !== 'INIT') {
    bar.innerHTML = `
      <div class="spinner"></div>
      <span class="action-message">正在处理，请稍候…</span>
    `;
    return;
  }

  // INTAKE_CONFIRMED → 生成大纲
  if (s === 'INTAKE_CONFIRMED') {
    const btn = makeBtn('生成大纲', async () => {
      btn.disabled = true; btn.textContent = '生成中…';
      try {
        await api.generateOutline(project.id);
        startPoll(project.id);
      } catch (e) {
        showError(e.message);
        btn.disabled = false; btn.textContent = '生成大纲';
      }
    });
    bar.appendChild(btn);
    return;
  }

  // OUTLINE_READY → 排版 & 渲染
  if (s === 'OUTLINE_READY') {
    const btn = makeBtn('排版 & 渲染', async () => {
      btn.disabled = true; btn.textContent = '渲染中…';
      try {
        await api.confirmOutline(project.id);
        startPoll(project.id);
      } catch (e) {
        showError(e.message);
        btn.disabled = false; btn.textContent = '排版 & 渲染';
      }
    });
    bar.appendChild(btn);
    return;
  }

  // READY_FOR_EXPORT → 导出 PDF
  if (s === 'READY_FOR_EXPORT') {
    const btn = makeBtn('导出 PDF', async () => {
      btn.disabled = true; btn.textContent = '导出中…';
      try {
        await api.exportPDF(project.id);
        startPoll(project.id);
      } catch (e) {
        showError(e.message);
        btn.disabled = false; btn.textContent = '导出 PDF';
      }
    });
    bar.appendChild(btn);
    return;
  }

  // EXPORTED → 下载链接
  if (s === 'EXPORTED' && project.error_message) {
    const a = document.createElement('a');
    a.href      = project.error_message;
    a.className = 'btn btn-primary';
    a.textContent = '⬇ 下载 PDF';
    a.download  = '';
    bar.appendChild(a);
  }
}

function makeBtn(text, onClick) {
  const btn = document.createElement('button');
  btn.className   = 'btn btn-primary';
  btn.textContent = text;
  btn.addEventListener('click', onClick);
  return btn;
}

function startPoll(id) {
  clearPoll();
  _pollTimer = setInterval(async () => {
    try {
      const p = await api.getProject(id);
      applyDetail(p);
      if (TERMINAL.has(p.status)) clearPoll();
    } catch { clearPoll(); }
  }, 3000);
}

// ─────────────────────────────────────────────────────────────────
// 幻灯片网格 + Lightbox
// ─────────────────────────────────────────────────────────────────
let _slides  = [];
let _lbIndex = 0;

async function loadSlides(projectId) {
  // 避免重复加载
  const section = document.getElementById('slides-section');
  if (!section || section.style.display !== 'none') return;

  try { _slides = await api.listSlides(projectId); }
  catch { return; }

  if (!_slides || !_slides.length) return;

  section.style.display = '';
  const grid = document.getElementById('slides-grid');
  grid.innerHTML = '';

  _slides.forEach((slide, i) => {
    const pad  = String(slide.slide_no).padStart(2, '0');
    const wrap = document.createElement('div');
    wrap.className = 'slide-thumb';
    wrap.innerHTML = `
      <img src="/slides-output/slide_${pad}.png" alt="Slide ${slide.slide_no}" loading="lazy"
           onerror="this.style.background='#e8e8e8';this.removeAttribute('src')">
      <div class="slide-thumb-label">P${slide.slide_no} ${esc(slide.title || '')}</div>
    `;
    wrap.onclick = () => openLightbox(i);
    grid.appendChild(wrap);
  });

  // Lightbox event listeners
  document.getElementById('lb-overlay').onclick = closeLightbox;
  document.getElementById('lb-prev').onclick = () => moveLightbox(-1);
  document.getElementById('lb-next').onclick = () => moveLightbox(+1);

  // Keyboard
  document.addEventListener('keydown', onLbKey);
}

function openLightbox(i) {
  _lbIndex = i;
  setLightboxImg();
  document.getElementById('lightbox').style.display = 'flex';
}

function closeLightbox() {
  document.getElementById('lightbox').style.display = 'none';
}

function moveLightbox(dir) {
  _lbIndex = (_lbIndex + dir + _slides.length) % _slides.length;
  setLightboxImg();
}

function setLightboxImg() {
  const pad = String(_slides[_lbIndex].slide_no).padStart(2, '0');
  document.getElementById('lb-img').src = `/slides-output/slide_${pad}.png`;
}

function onLbKey(e) {
  const lb = document.getElementById('lightbox');
  if (!lb || lb.style.display === 'none') return;
  if (e.key === 'Escape')     closeLightbox();
  if (e.key === 'ArrowLeft')  moveLightbox(-1);
  if (e.key === 'ArrowRight') moveLightbox(+1);
}

// ─────────────────────────────────────────────────────────────────
// 工具
// ─────────────────────────────────────────────────────────────────
function esc(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
