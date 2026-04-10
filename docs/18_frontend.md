# 前端开发文档 — PPT Agent Web UI

> 技术栈：纯 HTML5 + CSS3 + Vanilla JS（无构建工具）
> 托管方式：FastAPI `StaticFiles` 挂载
> 访问入口：`http://localhost:8000/app`

---

## 1. 目录结构

```
frontend/
├── index.html          # SPA 入口，包含所有 view 的 <template> 标签
├── style.css           # 全局样式（CSS 变量 + 组件样式）
└── app.js              # 应用逻辑（路由 / API / 轮询 / 渲染）
```

---

## 2. 后端配套修改

### 2.1 `main.py` — 挂载静态文件

```python
from pathlib import Path
from fastapi.staticfiles import StaticFiles

# 前端 SPA
app.mount("/app", StaticFiles(directory="frontend", html=True), name="frontend")

# 渲染输出目录（幻灯片 PNG 预览）
slides_dir = Path("tmp/e2e_output/slides")
slides_dir.mkdir(parents=True, exist_ok=True)
app.mount("/slides-output", StaticFiles(directory=str(slides_dir)), name="slides-output")
```

### 2.2 `api/routers/projects.py` — 新增项目列表接口

在文件顶部已有的路由之前插入：

```python
@router.get("", response_model=APIResponse[list[ProjectRead]])
def list_projects(db: Session = Depends(get_db)):
    """列出所有项目，按创建时间倒序。"""
    projects = db.query(Project).order_by(Project.created_at.desc()).all()
    return ok([ProjectRead.model_validate(p) for p in projects])
```

---

## 3. `index.html`

单页应用骨架。包含：顶部导航栏 + 主内容区 + 三个 `<template>` 视图模板。

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>PPT Agent</title>
  <link rel="stylesheet" href="style.css">
</head>
<body>

  <!-- 顶部导航 -->
  <nav class="navbar">
    <a class="brand" href="#/">PPT Agent</a>
    <a class="btn btn-primary" href="#/new">+ 新建项目</a>
  </nav>

  <!-- 主内容区（JS 渲染到此） -->
  <main id="app"></main>

  <!-- ── View Templates ───────────────────────── -->

  <!-- 视图 1：项目列表 -->
  <template id="tpl-project-list">
    <div class="view">
      <h2 class="view-title">我的项目</h2>
      <div id="project-grid" class="project-grid">
        <!-- JS 渲染项目卡片 -->
      </div>
      <p id="empty-hint" class="empty-hint" style="display:none">
        还没有项目，点击右上角新建。
      </p>
    </div>
  </template>

  <!-- 视图 2：新建项目（Brief 表单） -->
  <template id="tpl-new-project">
    <div class="view">
      <h2 class="view-title">新建项目</h2>
      <form id="brief-form" class="form-card">

        <div class="form-row">
          <label>项目名称 <span class="required">*</span></label>
          <input name="name" type="text" placeholder="苏州工业园区文化中心" required>
        </div>

        <div class="form-row">
          <label>建筑类型 <span class="required">*</span></label>
          <select name="building_type" required>
            <option value="">请选择</option>
            <option value="cultural_center">文化中心</option>
            <option value="museum">博物馆</option>
            <option value="office">办公楼</option>
            <option value="mixed_use">综合体</option>
            <option value="residential">住宅</option>
            <option value="education">教育建筑</option>
          </select>
        </div>

        <div class="form-row two-col">
          <div>
            <label>委托方 <span class="required">*</span></label>
            <input name="client_name" type="text" placeholder="苏州工业园区管委会" required>
          </div>
          <div>
            <label>城市</label>
            <input name="city" type="text" placeholder="苏州">
          </div>
        </div>

        <div class="form-row">
          <label>场地地址</label>
          <input name="site_address" type="text" placeholder="星湖街88号">
        </div>

        <div class="form-row two-col">
          <div>
            <label>总建筑面积（㎡）</label>
            <input name="gross_floor_area" type="number" placeholder="48000">
          </div>
          <div>
            <label>用地面积（㎡）</label>
            <input name="site_area" type="number" placeholder="18000">
          </div>
        </div>

        <div class="form-row">
          <label>风格偏好</label>
          <div class="checkbox-group">
            <label><input type="checkbox" name="style_preferences" value="现代主义"> 现代主义</label>
            <label><input type="checkbox" name="style_preferences" value="在地文化"> 在地文化</label>
            <label><input type="checkbox" name="style_preferences" value="绿色低碳"> 绿色低碳</label>
            <label><input type="checkbox" name="style_preferences" value="古典复兴"> 古典复兴</label>
            <label><input type="checkbox" name="style_preferences" value="极简主义"> 极简主义</label>
          </div>
        </div>

        <div class="form-row">
          <label>特殊要求</label>
          <textarea name="special_requirements" rows="3"
            placeholder="例如：需融入苏州园林元素，地下两层停车"></textarea>
        </div>

        <div class="form-actions">
          <a href="#/" class="btn btn-ghost">取消</a>
          <button type="submit" class="btn btn-primary" id="submit-btn">
            创建并开始 →
          </button>
        </div>

      </form>
    </div>
  </template>

  <!-- 视图 3：项目详情 -->
  <template id="tpl-project-detail">
    <div class="view">
      <div class="detail-header">
        <a href="#/" class="back-link">← 返回列表</a>
        <h2 class="view-title" id="detail-title">项目详情</h2>
        <span class="status-badge" id="detail-status"></span>
      </div>

      <!-- 进度 Stepper -->
      <div class="stepper" id="stepper">
        <div class="step" data-step="1">
          <div class="step-dot"></div>
          <div class="step-label">Brief 确认</div>
        </div>
        <div class="step-line"></div>
        <div class="step" data-step="2">
          <div class="step-dot"></div>
          <div class="step-label">大纲生成</div>
        </div>
        <div class="step-line"></div>
        <div class="step" data-step="3">
          <div class="step-dot"></div>
          <div class="step-label">页面排版</div>
        </div>
        <div class="step-line"></div>
        <div class="step" data-step="4">
          <div class="step-dot"></div>
          <div class="step-label">渲染截图</div>
        </div>
        <div class="step-line"></div>
        <div class="step" data-step="5">
          <div class="step-dot"></div>
          <div class="step-label">PDF 导出</div>
        </div>
      </div>

      <!-- 操作按钮区 -->
      <div class="action-bar" id="action-bar"></div>

      <!-- 幻灯片网格（渲染后显示） -->
      <section id="slides-section" style="display:none">
        <h3 class="section-title">幻灯片预览</h3>
        <div class="slides-grid" id="slides-grid"></div>
      </section>

      <!-- Lightbox -->
      <div class="lightbox" id="lightbox" style="display:none">
        <div class="lightbox-overlay" id="lb-close"></div>
        <img class="lightbox-img" id="lb-img" src="" alt="">
        <button class="lb-btn lb-prev" id="lb-prev">‹</button>
        <button class="lb-btn lb-next" id="lb-next">›</button>
      </div>

    </div>
  </template>

  <script src="app.js"></script>
</body>
</html>
```

---

## 4. `style.css`

```css
/* ── Design Tokens（复用幻灯片配色） ── */
:root {
  --primary:       #1C3A5F;
  --secondary:     #2D6A8F;
  --accent:        #E8A020;
  --bg:            #F8F6F1;
  --surface:       #EDEAE3;
  --border:        #D4D0C8;
  --text:          #1C1C1C;
  --text-muted:    #6B6B6B;
  --danger:        #C0392B;
  --success:       #27AE60;

  --radius:        6px;
  --shadow:        0 2px 8px rgba(0,0,0,0.08);
  --transition:    0.15s ease;

  --font-heading:  "PingFang SC", "Microsoft YaHei", sans-serif;
  --font-body:     "PingFang SC", "Microsoft YaHei", sans-serif;
}

/* ── Reset ── */
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
body { background: var(--bg); color: var(--text); font-family: var(--font-body);
       font-size: 15px; line-height: 1.6; }
a { color: inherit; text-decoration: none; }

/* ── Navbar ── */
.navbar {
  position: sticky; top: 0; z-index: 100;
  background: var(--primary); color: #fff;
  display: flex; align-items: center; justify-content: space-between;
  padding: 0 32px; height: 56px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.2);
}
.brand { font-size: 18px; font-weight: 700; letter-spacing: 0.02em; }

/* ── View ── */
.view { max-width: 960px; margin: 0 auto; padding: 40px 24px 80px; }
.view-title { font-size: 24px; font-weight: 700; margin-bottom: 24px; }

/* ── Buttons ── */
.btn {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 10px 20px; border-radius: var(--radius);
  font-size: 14px; font-weight: 600; cursor: pointer;
  border: none; transition: var(--transition);
}
.btn-primary { background: var(--accent); color: #fff; }
.btn-primary:hover { background: #d08f18; }
.btn-ghost { background: transparent; color: var(--text); border: 1px solid var(--border); }
.btn-ghost:hover { background: var(--surface); }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }

/* ── Project Grid ── */
.project-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 16px; }
.project-card {
  background: #fff; border: 1px solid var(--border); border-radius: var(--radius);
  padding: 20px; cursor: pointer; transition: var(--transition);
}
.project-card:hover { box-shadow: var(--shadow); border-color: var(--secondary); }
.project-card-name { font-size: 16px; font-weight: 600; margin-bottom: 8px; }
.project-card-meta { font-size: 13px; color: var(--text-muted); }

/* ── Status Badge ── */
.status-badge {
  display: inline-block; padding: 3px 10px; border-radius: 20px;
  font-size: 12px; font-weight: 600;
}
.status-brief_ready       { background: #EBF5FB; color: #2E86C1; }
.status-outline_ready     { background: #E9F7EF; color: #1E8449; }
.status-rendered          { background: #FEF9E7; color: #D4AC0D; }
.status-exported          { background: #E8F8F5; color: #148F77; }
.status-in_progress       { background: #FDFEFE; color: var(--text-muted); }

/* ── Form ── */
.form-card {
  background: #fff; border: 1px solid var(--border); border-radius: var(--radius);
  padding: 32px; display: flex; flex-direction: column; gap: 20px;
}
.form-row { display: flex; flex-direction: column; gap: 6px; }
.form-row.two-col { flex-direction: row; gap: 16px; }
.form-row.two-col > * { flex: 1; display: flex; flex-direction: column; gap: 6px; }
label { font-size: 14px; font-weight: 600; }
.required { color: var(--danger); }
input[type=text], input[type=number], select, textarea {
  width: 100%; padding: 10px 12px; border: 1px solid var(--border);
  border-radius: var(--radius); font-size: 14px; font-family: inherit;
  background: var(--bg); transition: var(--transition);
}
input:focus, select:focus, textarea:focus {
  outline: none; border-color: var(--secondary);
  box-shadow: 0 0 0 3px rgba(45,106,143,0.12);
}
.checkbox-group { display: flex; flex-wrap: wrap; gap: 12px; padding-top: 4px; }
.checkbox-group label { font-weight: 400; display: flex; align-items: center; gap: 6px; cursor: pointer; }
.form-actions { display: flex; justify-content: flex-end; gap: 12px; padding-top: 8px; }

/* ── Stepper ── */
.stepper {
  display: flex; align-items: center; margin: 8px 0 32px;
  background: #fff; border: 1px solid var(--border);
  border-radius: var(--radius); padding: 20px 24px;
}
.step { display: flex; flex-direction: column; align-items: center; gap: 8px; min-width: 80px; }
.step-dot {
  width: 28px; height: 28px; border-radius: 50%;
  border: 2px solid var(--border); background: #fff;
  display: flex; align-items: center; justify-content: center;
  transition: var(--transition);
}
.step.done .step-dot  { background: var(--success); border-color: var(--success); }
.step.done .step-dot::after { content: "✓"; color: #fff; font-size: 13px; font-weight: 700; }
.step.active .step-dot { border-color: var(--accent); background: var(--accent); }
.step.active .step-dot::after { content: ""; width: 8px; height: 8px; border-radius: 50%; background: #fff; }
.step-label { font-size: 12px; color: var(--text-muted); text-align: center; }
.step.done .step-label, .step.active .step-label { color: var(--text); font-weight: 600; }
.step-line { flex: 1; height: 2px; background: var(--border); transition: var(--transition); }
.step-line.done { background: var(--success); }

/* ── Action Bar ── */
.action-bar { margin-bottom: 32px; display: flex; align-items: center; gap: 16px; min-height: 44px; }
.action-message { font-size: 14px; color: var(--text-muted); }
.spinner {
  width: 18px; height: 18px; border: 2px solid var(--border);
  border-top-color: var(--accent); border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* ── Slides Grid ── */
.section-title { font-size: 18px; font-weight: 700; margin-bottom: 16px; }
.slides-grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 12px;
}
.slide-thumb {
  background: var(--surface); border: 1px solid var(--border);
  border-radius: var(--radius); overflow: hidden; cursor: pointer;
  transition: var(--transition); aspect-ratio: 16/9;
}
.slide-thumb:hover { box-shadow: var(--shadow); transform: translateY(-2px); }
.slide-thumb img { width: 100%; height: 100%; object-fit: cover; }
.slide-thumb-label {
  padding: 6px 10px; font-size: 11px; color: var(--text-muted);
  border-top: 1px solid var(--border); background: #fff;
}

/* ── Lightbox ── */
.lightbox { position: fixed; inset: 0; z-index: 200; display: flex; align-items: center; justify-content: center; }
.lightbox-overlay { position: absolute; inset: 0; background: rgba(0,0,0,0.85); }
.lightbox-img { position: relative; max-width: 90vw; max-height: 90vh; border-radius: 4px; }
.lb-btn {
  position: absolute; top: 50%; transform: translateY(-50%);
  background: rgba(255,255,255,0.15); color: #fff; border: none;
  width: 44px; height: 44px; border-radius: 50%; font-size: 24px;
  cursor: pointer; z-index: 201; transition: var(--transition);
}
.lb-btn:hover { background: rgba(255,255,255,0.3); }
.lb-prev { left: 24px; }
.lb-next { right: 24px; }

/* ── Detail Header ── */
.detail-header { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; }
.back-link { font-size: 14px; color: var(--secondary); }
.back-link:hover { text-decoration: underline; }
.detail-header .view-title { margin-bottom: 0; flex: 1; }

/* ── Misc ── */
.empty-hint { color: var(--text-muted); text-align: center; padding: 60px 0; }
.error-msg { background: #FDEDEC; border: 1px solid #E74C3C; border-radius: var(--radius);
             padding: 12px 16px; color: #922B21; font-size: 14px; margin-bottom: 16px; }
```

---

## 5. `app.js`

```javascript
/* ── PPT Agent SPA ── */
'use strict';

const BASE = '';   // 同源，FastAPI 在 localhost:8000

// ─────────────────────────────────────────
// API 层
// ─────────────────────────────────────────
const api = {
  async _fetch(method, path, body) {
    const opts = {
      method,
      headers: { 'Content-Type': 'application/json' },
    };
    if (body) opts.body = JSON.stringify(body);
    const res = await fetch(BASE + path, opts);
    const json = await res.json();
    if (!json.success) throw new Error(json.error || '请求失败');
    return json.data;
  },

  listProjects:     ()         => api._fetch('GET',   '/projects'),
  getProject:       (id)       => api._fetch('GET',   `/projects/${id}`),
  createProject:    (body)     => api._fetch('POST',  '/projects', body),
  updateBrief:      (id, body) => api._fetch('PATCH', `/projects/${id}/brief`, body),
  confirmBrief:     (id)       => api._fetch('POST',  `/projects/${id}/confirm-brief`),
  generateOutline:  (id)       => api._fetch('POST',  `/projects/${id}/outline/generate`),
  renderSlides:     (id)       => api._fetch('POST',  `/render`, { project_id: id }),
  listSlides:       (id)       => api._fetch('GET',   `/projects/${id}/slides`),
  exportPDF:        (id)       => api._fetch('POST',  `/projects/${id}/export`, { export_type: 'pdf' }),
};

// ─────────────────────────────────────────
// 路由
// ─────────────────────────────────────────
const routes = {
  '/':            renderProjectList,
  '/new':         renderNewProject,
  '/project/:id': renderProjectDetail,
};

function getRoute(hash) {
  const path = hash.replace('#', '') || '/';
  for (const [pattern, fn] of Object.entries(routes)) {
    if (pattern.includes(':')) {
      const prefix = pattern.split('/:')[0];
      if (path.startsWith(prefix + '/')) {
        const param = path.slice(prefix.length + 1);
        return { fn, params: { id: param } };
      }
    } else if (path === pattern) {
      return { fn, params: {} };
    }
  }
  return { fn: renderProjectList, params: {} };
}

let _pollTimer = null;

function navigate(hash) {
  clearPoll();
  window.location.hash = hash;
}

function clearPoll() {
  if (_pollTimer) { clearInterval(_pollTimer); _pollTimer = null; }
}

window.addEventListener('hashchange', () => {
  clearPoll();
  const { fn, params } = getRoute(window.location.hash);
  fn(params);
});

window.addEventListener('DOMContentLoaded', () => {
  const { fn, params } = getRoute(window.location.hash);
  fn(params);
});

// ─────────────────────────────────────────
// 辅助
// ─────────────────────────────────────────
function cloneTemplate(id) {
  return document.getElementById(id).content.cloneNode(true);
}

function showError(msg) {
  const el = document.createElement('div');
  el.className = 'error-msg';
  el.textContent = msg;
  document.getElementById('app').prepend(el);
  setTimeout(() => el.remove(), 5000);
}

const STATUS_LABELS = {
  init:           '初始化',
  brief_ready:    'Brief 已确认',
  outline_ready:  '大纲已生成',
  slides_planned: '排版完成',
  rendered:       '渲染完成',
  exported:       '已导出',
};
function statusLabel(s) { return STATUS_LABELS[s] || s; }
function statusClass(s) {
  if (s?.endsWith('_in_progress') || s === 'init') return 'in_progress';
  return s || 'in_progress';
}

// ─────────────────────────────────────────
// View 1：项目列表
// ─────────────────────────────────────────
async function renderProjectList() {
  const frag = cloneTemplate('tpl-project-list');
  document.getElementById('app').innerHTML = '';
  document.getElementById('app').appendChild(frag);

  let projects = [];
  try { projects = await api.listProjects(); } catch(e) { showError(e.message); return; }

  const grid = document.getElementById('project-grid');
  const hint = document.getElementById('empty-hint');

  if (!projects.length) { hint.style.display = 'block'; return; }

  projects.forEach(p => {
    const card = document.createElement('div');
    card.className = 'project-card';
    card.innerHTML = `
      <div class="project-card-name">${p.name}</div>
      <div class="project-card-meta" style="margin-bottom:12px;">
        <span class="status-badge status-${statusClass(p.status)}">${statusLabel(p.status)}</span>
      </div>
      <div class="project-card-meta">${p.created_at?.slice(0,10) || ''}</div>
    `;
    card.onclick = () => navigate(`#/project/${p.id}`);
    grid.appendChild(card);
  });
}

// ─────────────────────────────────────────
// View 2：新建项目（Brief 表单）
// ─────────────────────────────────────────
function renderNewProject() {
  const frag = cloneTemplate('tpl-new-project');
  document.getElementById('app').innerHTML = '';
  document.getElementById('app').appendChild(frag);

  document.getElementById('brief-form').addEventListener('submit', async e => {
    e.preventDefault();
    const form = e.target;
    const btn  = document.getElementById('submit-btn');
    btn.disabled = true;
    btn.textContent = '创建中…';

    const data   = Object.fromEntries(new FormData(form));
    const styles = [...form.querySelectorAll('[name=style_preferences]:checked')].map(cb => cb.value);

    try {
      // Step 1: 创建项目
      const project = await api.createProject({ name: data.name, status: 'init' });

      // Step 2: 填写 Brief
      await api.updateBrief(project.id, {
        raw_text: [
          data.building_type        && `建筑类型：${data.building_type}`,
          data.client_name          && `委托方：${data.client_name}`,
          data.city                 && `城市：${data.city}`,
          data.site_address         && `地址：${data.site_address}`,
          data.gross_floor_area     && `总建筑面积：${data.gross_floor_area}㎡`,
          data.site_area            && `用地面积：${data.site_area}㎡`,
          styles.length             && `风格偏好：${styles.join('、')}`,
          data.special_requirements && `特殊要求：${data.special_requirements}`,
        ].filter(Boolean).join('\n'),
      });

      // Step 3: 确认 Brief
      await api.confirmBrief(project.id);

      navigate(`#/project/${project.id}`);
    } catch(err) {
      showError(err.message);
      btn.disabled    = false;
      btn.textContent = '创建并开始 →';
    }
  });
}

// ─────────────────────────────────────────
// View 3：项目详情
// ─────────────────────────────────────────
const STATUS_STEP = {
  brief_ready:    1,
  outline_ready:  2,
  slides_planned: 3,
  rendered:       4,
  exported:       5,
};

async function renderProjectDetail({ id }) {
  const frag = cloneTemplate('tpl-project-detail');
  document.getElementById('app').innerHTML = '';
  document.getElementById('app').appendChild(frag);

  let project;
  try { project = await api.getProject(id); } catch(e) { showError(e.message); return; }

  applyProjectDetail(project);

  // 轮询：非终态时每 3 秒刷新
  const terminal = ['brief_ready', 'outline_ready', 'slides_planned', 'rendered', 'exported'];
  if (!terminal.includes(project.status)) {
    _pollTimer = setInterval(async () => {
      try {
        project = await api.getProject(id);
        applyProjectDetail(project);
        if (terminal.includes(project.status)) clearPoll();
      } catch { clearPoll(); }
    }, 3000);
  }
}

function applyProjectDetail(project) {
  document.getElementById('detail-title').textContent = project.name;
  const badge = document.getElementById('detail-status');
  badge.textContent = statusLabel(project.status);
  badge.className   = `status-badge status-${statusClass(project.status)}`;

  // Stepper
  const currentStep = STATUS_STEP[project.status] ?? 0;
  document.querySelectorAll('.step').forEach(el => {
    const s = parseInt(el.dataset.step);
    el.classList.toggle('done',   s < currentStep);
    el.classList.toggle('active', s === currentStep);
  });
  document.querySelectorAll('.step-line').forEach((el, i) => {
    el.classList.toggle('done', (i + 1) < currentStep);
  });

  renderActionBar(project);

  if (project.status === 'rendered' || project.status === 'exported') {
    loadSlides(project.id);
  }
}

function renderActionBar(project) {
  const bar = document.getElementById('action-bar');
  bar.innerHTML = '';

  if (project.status?.endsWith('_in_progress')) {
    bar.innerHTML = `<div class="spinner"></div><span class="action-message">正在处理，请稍候…</span>`;
    return;
  }

  if (project.status === 'brief_ready') {
    const btn = mkBtn('生成大纲', 'btn-primary', async () => {
      btn.disabled = true; btn.textContent = '生成中…';
      try { await api.generateOutline(project.id); startPoll(project.id); }
      catch(e) { showError(e.message); btn.disabled = false; btn.textContent = '生成大纲'; }
    });
    bar.appendChild(btn);
    return;
  }

  if (project.status === 'outline_ready') {
    const btn = mkBtn('排版 & 渲染', 'btn-primary', async () => {
      btn.disabled = true; btn.textContent = '渲染中…';
      try { await api.renderSlides(project.id); startPoll(project.id); }
      catch(e) { showError(e.message); btn.disabled = false; btn.textContent = '排版 & 渲染'; }
    });
    bar.appendChild(btn);
    return;
  }

  if (project.status === 'rendered') {
    const btn = mkBtn('导出 PDF', 'btn-primary', async () => {
      btn.disabled = true; btn.textContent = '导出中…';
      try { await api.exportPDF(project.id); startPoll(project.id); }
      catch(e) { showError(e.message); btn.disabled = false; btn.textContent = '导出 PDF'; }
    });
    bar.appendChild(btn);
    return;
  }

  if (project.status === 'exported' && project.export_url) {
    const a = document.createElement('a');
    a.href = project.export_url;
    a.className = 'btn btn-primary';
    a.textContent = '⬇ 下载 PDF';
    a.download = '';
    bar.appendChild(a);
  }
}

function mkBtn(text, cls, onClick) {
  const btn = document.createElement('button');
  btn.className = `btn ${cls}`;
  btn.textContent = text;
  btn.addEventListener('click', onClick);
  return btn;
}

function startPoll(id) {
  clearPoll();
  const terminal = ['brief_ready', 'outline_ready', 'slides_planned', 'rendered', 'exported'];
  _pollTimer = setInterval(async () => {
    try {
      const p = await api.getProject(id);
      applyProjectDetail(p);
      if (terminal.includes(p.status)) clearPoll();
    } catch { clearPoll(); }
  }, 3000);
}

// ─── 幻灯片网格 ───
let _slides  = [];
let _lbIndex = 0;

async function loadSlides(projectId) {
  try { _slides = await api.listSlides(projectId); } catch { return; }

  const section = document.getElementById('slides-section');
  const grid    = document.getElementById('slides-grid');
  section.style.display = '';
  grid.innerHTML = '';

  _slides.forEach((slide, i) => {
    const padded = String(slide.slide_no).padStart(2, '0');
    const wrap   = document.createElement('div');
    wrap.className = 'slide-thumb';
    wrap.innerHTML = `
      <img src="/slides-output/slide_${padded}.png" alt="Slide ${slide.slide_no}" loading="lazy">
      <div class="slide-thumb-label">P${slide.slide_no}  ${slide.title || ''}</div>
    `;
    wrap.onclick = () => openLightbox(i);
    grid.appendChild(wrap);
  });
}

function openLightbox(index) {
  _lbIndex = index;
  document.getElementById('lightbox').style.display = 'flex';
  updateLightboxImg();
  document.getElementById('lb-close').onclick = closeLightbox;
  document.getElementById('lb-prev').onclick  = () => { _lbIndex = (_lbIndex - 1 + _slides.length) % _slides.length; updateLightboxImg(); };
  document.getElementById('lb-next').onclick  = () => { _lbIndex = (_lbIndex + 1) % _slides.length; updateLightboxImg(); };
}

function updateLightboxImg() {
  const padded = String(_slides[_lbIndex].slide_no).padStart(2, '0');
  document.getElementById('lb-img').src = `/slides-output/slide_${padded}.png`;
}

function closeLightbox() {
  document.getElementById('lightbox').style.display = 'none';
}
```

---

## 6. 关键文件汇总

| 文件 | 行为 |
|------|------|
| `frontend/index.html` | SPA shell，3 个 `<template>` 视图 |
| `frontend/style.css`  | CSS 变量 + 全局组件样式 |
| `frontend/app.js`     | 路由 / API / 轮询 / 幻灯片网格 + Lightbox |
| `main.py`             | 新增 `StaticFiles` 挂载（/app, /slides-output）|
| `api/routers/projects.py` | 新增 `GET /projects` 接口 |

---

## 7. 验证步骤

```bash
# 启动服务
.venv/Scripts/python.exe -m uvicorn main:app --reload

# 浏览器访问
http://localhost:8000/app
```

1. 首页显示项目列表（包括 e2e 测试遗留项目）
2. 新建项目 → 填写 Brief 表单 → 提交 → 自动跳转详情页
3. 详情页 Stepper 显示"Brief 确认"高亮
4. 点击"生成大纲" → 按钮变灰 + 轮询 → Stepper 自动推进
5. 点击"排版 & 渲染" → 等待 → 幻灯片网格出现
6. 点击任意缩略图 → Lightbox 打开，左右箭头翻页
7. 点击"导出 PDF" → 完成后出现下载链接
