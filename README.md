# cpa-codex-cleanup

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-22c55e.svg)](./LICENSE)
[![UI](https://img.shields.io/badge/Web_UI-Real--time_Log-0b6cf0)](http://127.0.0.1:8123)

面向 CPA 管理接口的清理工具，提供 Web 控制台、一键执行、实时进度日志和统计结果。

<p align="center">
  <img width="1138" height="745" alt="cpa-codex-cleanup-ui" src="https://github.com/user-attachments/assets/a11fc24e-6f85-4e64-8da7-9e8932d5b08f" />
</p>

## Highlights

- Web UI 实时显示执行日志与进度
- 支持规则命中清理、主动探测、401 补删
- 任务异步执行，接口可轮询获取状态
- 默认本地启动，开箱即用

## 3 分钟快速开始

> 先下载项目，再运行一键脚本。

### 1) 下载项目

方式 A：Git 克隆

```bash
git clone https://github.com/qcmuu/cpa-codex-cleanup.git
cd cpa-codex-cleanup
```

方式 B：下载 ZIP

- 直链下载：`https://github.com/qcmuu/cpa-codex-cleanup/archive/refs/heads/main.zip`
- 下载后解压并进入项目目录

### 2) 安装依赖

```bash
pip install curl_cffi
```

### 3) 一键启动（Windows）

双击 [`run_cpa_codex_cleanup.bat`](./run_cpa_codex_cleanup.bat)  
或终端执行：

```powershell
.\run_cpa_codex_cleanup.bat
```

启动后访问：`http://127.0.0.1:8123`

## 使用教程

1. 打开 `http://127.0.0.1:8123`
2. 输入 `Management Token`
3. `Management URL` 使用默认值，或填写你的管理地址（默认：`http://127.0.0.1:8317/management.html`）
4. 按需调整并发和超时参数
5. 点击 `执行清理`
6. 观察右侧 `实时日志`
7. 查看统计结果（扫描数、命中数、删除数、失败数）

## 配置说明

| 参数 | 默认值 | 说明 |
|---|---|---|
| `management_url` | `http://127.0.0.1:8317/management.html` | 管理地址。内部会自动转换为 API 根路径 |
| `management_token` | `management_token` | 管理 token（前端输入时不带 `Bearer `） |
| `management_timeout` | `15` | 管理接口超时（秒） |
| `active_probe` | `true` | 是否开启主动探测 |
| `probe_timeout` | `8` | 探测超时（秒） |
| `probe_workers` | `12` | 探测并发数 |
| `delete_workers` | `8` | 删除并发数 |
| `max_active_probes` | `120` | 最多主动探测数量，`0` 表示不探测 |

## 手动启动

```bash
python cpa_codex_cleanup_web.py --host 127.0.0.1 --port 8123
```

## API 一览

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/api/defaults` | 获取默认配置 |
| `POST` | `/api/tasks` | 提交清理任务 |
| `GET` | `/api/tasks/{task_id}` | 查询任务状态、日志和结果 |

任务状态：

- `running` 执行中
- `completed` 执行完成
- `failed` 执行失败

## 项目结构

```text
.
├─ cpa_codex_cleanup_engine.py
├─ cpa_codex_cleanup_web.py
├─ run_cpa_codex_cleanup.bat
├─ web/
│  └─ index.html
├─ README.md
└─ LICENSE
```

## 常见问题

### `HTTP 401 Unauthorized`

`management_token` 无效或已失效。

### `HTTP 404 Not Found`

`management_url` 错误。请确认使用管理根路径，或直接使用默认 `.../management.html`。

### 日志没有更新

- 确认服务仍在运行
- 确认任务提交成功
- 检查对应 `task_id` 状态是否为 `running`

## License

MIT License
