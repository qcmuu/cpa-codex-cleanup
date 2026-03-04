# cpa-codex-cleanup

一个面向 CPA 管理接口的开源清理工具，提供：

- Web 可视化操作界面
- 一键执行清理任务
- 实时日志与进度查看
- 清理结果统计（扫描数、命中数、删除数、失败数）

项目适合个人维护与团队协作，也适合 fork 后二次开发。

## 功能概览

- 支持按规则识别异常 token
- 支持可选主动探测（用于识别潜在失效 token）
- 支持额外 401 补删
- 支持并发探测与并发删除
- 支持任务异步执行与轮询查询

## 项目结构

```text
.
├─ cpa_codex_cleanup_engine.py   # 清理引擎核心逻辑
├─ cpa_codex_cleanup_web.py      # Web UI 后端（任务管理 + HTTP API）
├─ web/
│  └─ index.html           # Web UI 前端
├─ run_cpa_codex_cleanup.bat     # Windows 一键启动脚本
└─ README.md
```

## 环境要求

- Python 3.10+
- 依赖：
  - `curl_cffi`

安装依赖示例：

```bash
pip install curl_cffi
```

## 一键启动（Windows）

直接双击：

- `run_cpa_codex_cleanup.bat`

或在终端执行：

```powershell
.\run_cpa_codex_cleanup.bat
```

默认地址：

- `http://127.0.0.1:8123`

## 手动启动

```bash
python cpa_codex_cleanup_web.py --host 127.0.0.1 --port 8123
```

## Web 使用说明

1. 打开 `http://127.0.0.1:8123`
2. 填写 `Management URL`（默认 `http://127.0.0.1:8317/management.html`）
3. 填写 `Management Token`
4. 点击 `执行清理`
5. 在右侧实时日志面板查看执行进度

## 后端 API（给二次开发用）

- `GET /api/defaults`
  - 获取默认配置
- `POST /api/tasks`
  - 提交清理任务
- `GET /api/tasks/{task_id}`
  - 查询任务状态和日志

状态说明：

- `running`：执行中
- `completed`：执行完成
- `failed`：执行失败

## 常见问题

### 1) `HTTP 401 Unauthorized`

通常是 `management_token` 不正确或已失效。

### 2) `HTTP 404 Not Found`

通常是 `management_url` 不正确。  
请确认它是管理 API 根路径，而不是页面地址或子接口地址。

### 3) 日志没变化

请检查：

- 服务是否在运行
- 任务是否真的提交成功
- `task_id` 对应任务状态是否仍为 `running`

## Fork 与协作

### Fork

1. 在 GitHub 点击 `Fork`
2. 克隆你自己的仓库

```bash
git clone <your-fork-url>
cd <repo>
```

3. 新建分支开发

```bash
git checkout -b feat/your-feature
```

4. 提交并推送

```bash
git add .
git commit -m "feat: add xxx"
git push origin feat/your-feature
```

5. 发起 Pull Request

### 建议规范

- 提交信息建议使用 `feat/fix/refactor/docs/chore` 前缀
- 重要改动请在 PR 描述里说明影响范围与回滚方案
- 涉及安全或 token 处理改动请重点评审

## 安全建议

- 不要把真实 token 写死到代码
- 不要把 token 提交到 Git 仓库
- 生产环境建议通过环境变量注入敏感信息

## 许可证

建议使用 MIT License。  
如果你准备公开发布，请补充 `LICENSE` 文件后再对外共享。
