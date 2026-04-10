---
tags: [api, routes, fastapi]
source: main.py, api/routers/
---

# API 路由索引

> FastAPI 服务所有路由，项目启动入口：`main.py`

## 路由注册（main.py）

```python
app.include_router(material_packages.router)
app.include_router(outlines.router)
app.include_router(render_router.router)
app.include_router(exports.router)
app.include_router(projects.router)
app.include_router(assets.router)
app.include_router(slides.router)
app.include_router(visual_themes.router)
```

---

## 素材包 API（`api/routers/material_packages.py`）

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/projects/{id}/material-packages/ingest-local` | **阶段一入口**：从本地目录摄入素材 |
| `POST` | `/projects/{id}/material-packages/{pkg_id}/regenerate` | **阶段二+三入口**：重新生成 Brief + Outline |
| `GET` | `/projects/{id}/material-packages` | 列出所有素材包 |
| `GET` | `/projects/{id}/material-packages/{pkg_id}` | 获取素材包详情 |

---

## 大纲 API（`api/routers/outlines.py`）

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/projects/{id}/outline` | 获取当前大纲 |
| `POST` | `/projects/{id}/outline/confirm` | **阶段四+五入口**：确认大纲，触发编排流水线 |
| `PUT` | `/projects/{id}/outline/{outline_id}` | 更新大纲（手动编辑） |

---

## 渲染与审查 API（`api/routers/render.py`）

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/projects/{id}/render` | **阶段七入口**：触发渲染 |
| `POST` | `/projects/{id}/review` | **阶段八入口**：触发审查 |
| `GET` | `/projects/{id}/slides/{no}/screenshot` | 获取截图 |

---

## 导出 API（`api/routers/exports.py`）

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/projects/{id}/export` | **阶段九入口**：触发 PDF 导出 |
| `GET` | `/projects/{id}/export/status` | 查询导出状态 |
| `GET` | `/projects/{id}/export/download` | 下载 PDF |

---

## 其他 API

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/projects` | 创建新项目 |
| `GET` | `/projects/{id}` | 获取项目状态 |
| `GET` | `/projects/{id}/assets` | 列出所有资产 |
| `GET` | `/projects/{id}/slides` | 列出所有幻灯片 |
| `POST` | `/projects/{id}/visual-theme` | 生成/更新视觉主题 |

## 中间件

- `api/middleware.py` — 请求日志 + 错误捕获
- `api/response.py` — 统一响应格式
- `api/exceptions.py` — 错误码定义（详见 `docs/12_error_codes.md`）

## 相关

- [[tasks-infra/BackgroundWorkers]]
- [[enums/ProjectStatus]]
