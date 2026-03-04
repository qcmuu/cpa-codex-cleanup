# cpa-codex-cleanup
<img width="1138" height="745" alt="image" src="https://github.com/user-attachments/assets/a11fc24e-6f85-4e64-8da7-9e8932d5b08f" />
一个面向 CPA 管理接口的开源清理工具，提供：

- Web 可视化操作界面
- 一键执行清理任务
- 实时日志与进度查看
- 清理结果统计（扫描数、命中数、删除数、失败数）

项目适合个人维护与团队协作，也适合二次开发。
## 功能概览

- 按规则识别异常 token
- 可选主动探测（识别潜在失效 token）
- 额外 401 补删
- 并发探测与并发删除
- 异步任务执行与轮询查询

## 项目结构

```text
.
├─ cpa_codex_cleanup_engine.py      # 清理引擎核心逻辑
├─ cpa_codex_cleanup_web.py         # Web UI 后端（任务管理 + HTTP API）
├─ web/
│  └─ index.html                    # Web UI 前端
├─ run_cpa_codex_cleanup.bat        # Windows 一键启动脚本
├─ README.md
└─ LICENSE
```

## 环境要求

- Python 3.10+
- 依赖库：`curl_cffi`

安装依赖：

```bash
pip install curl_cffi
```

## 快速开始（必须先下载项目）

运行一键脚本前，必须先把项目下载到本地。

### 1) 下载项目

方式 A：Git 克隆

```bash
git clone https://github.com/qcmuu/cpa-codex-cleanup.git
cd cpa-codex-cleanup
```

方式 B：下载 ZIP

1. 打开仓库主页：`https://github.com/qcmuu/cpa-codex-cleanup`
2. 点击页面右上方 `<> Code`（中文界面为“代码”）-> `Download ZIP`
3. 或直接下载：`https://github.com/qcmuu/cpa-codex-cleanup/archive/refs/heads/main.zip`
4. 解压 ZIP 后进入项目目录

### 2) 安装依赖

```bash
pip install curl_cffi
```

### 3) 一键启动（Windows）

双击 `run_cpa_codex_cleanup.bat`，或在终端执行：

```powershell
.\run_cpa_codex_cleanup.bat
```

启动后默认访问：

- `http://127.0.0.1:8123`

## 手动启动

```bash
python cpa_codex_cleanup_web.py --host 127.0.0.1 --port 8123
```

## Web 使用教程

1. 打开 `http://127.0.0.1:8123`
2. `Management URL` 保持默认或改为你的管理页地址（默认：`http://127.0.0.1:8317/management.html`）
3. 输入 `Management Token`（不带 `Bearer ` 前缀）
4. 按需调整并发与超时参数
5. 点击 `执行清理`
6. 右侧 `实时日志` 查看进度
7. 下方统计卡片查看结果：
- 扫描总数
- 命中数量
- 主流程删除
- 401 补删
- 总删除
- 失败数

## 后端 API（供二次开发）

- `GET /api/defaults`：获取默认配置
- `POST /api/tasks`：提交清理任务
- `GET /api/tasks/{task_id}`：查询任务状态与日志

状态值：

- `running`：执行中
- `completed`：执行完成
- `failed`：执行失败

## 常见问题

### 1) `HTTP 401 Unauthorized`

通常是 `management_token` 不正确或已失效。

### 2) `HTTP 404 Not Found`

通常是 `management_url` 不正确。  
请确认填写的是管理接口根路径（或可自动转换的 `.../management.html`）。

### 3) 日志没有更新

请依次检查：

- 服务是否正在运行
- 任务是否已成功提交
- 对应 `task_id` 状态是否仍为 `running`

## 许可证

MIT License
