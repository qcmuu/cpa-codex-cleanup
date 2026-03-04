
#!/usr/bin/env python3
"""Rewritten CPA cleanup Web UI backend with async job progress."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import threading
import time
import traceback
import uuid
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
ENGINE_SCRIPT = ROOT / "cpa_cleanup_engine.py"
INDEX_HTML = ROOT / "web" / "index.html"


@dataclass
class TaskState:
    task_id: str
    status: str = "running"
    created_at: float = field(default_factory=time.time)
    started_at: float = field(default_factory=time.time)
    ended_at: float = 0.0
    logs: list[str] = field(default_factory=list)
    summary: dict[str, Any] | None = None
    error: str = ""

    def add_log(self, line: str) -> None:
        stamp = time.strftime("%H:%M:%S", time.localtime())
        self.logs.append(f"[{stamp}] {line}")
        if len(self.logs) > 4000:
            self.logs = self.logs[-4000:]


class CleanupEngineHost:
    def __init__(self, script_path: Path):
        self.script_path = script_path
        self.module: Any | None = None
        self.module_lock = threading.Lock()
        self.task_lock = threading.Lock()
        self.tasks: dict[str, TaskState] = {}
        self.running_task_id: str | None = None

    def _load_module(self):
        with self.module_lock:
            if self.module is not None:
                return self.module

            if not self.script_path.exists():
                raise FileNotFoundError(f"engine script not found: {self.script_path}")

            spec = importlib.util.spec_from_file_location("cpa_cleanup_engine", str(self.script_path))
            if not spec or not spec.loader:
                raise RuntimeError("failed to load cleanup engine script")

            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
            self.module = module
            return module

    def defaults(self) -> dict[str, Any]:
        module = self._load_module()
        fn = getattr(module, "web_defaults", None)
        if not callable(fn):
            raise RuntimeError("cleanup engine missing web_defaults()")
        data = fn()
        if not isinstance(data, dict):
            raise RuntimeError("web_defaults() must return dict")
        return data

    def launch_task(self, payload: dict[str, Any]) -> tuple[bool, int, dict[str, Any]]:
        with self.task_lock:
            if self.running_task_id:
                running = self.tasks.get(self.running_task_id)
                if running and running.status == "running":
                    return False, HTTPStatus.CONFLICT, {
                        "ok": False,
                        "error": "已有任务在执行，请等待完成。",
                        "task_id": running.task_id,
                    }
                self.running_task_id = None

            task_id = uuid.uuid4().hex
            task = TaskState(task_id=task_id)
            self.tasks[task_id] = task
            self.running_task_id = task_id

        thread = threading.Thread(target=self._run_task, args=(task_id, payload), daemon=True)
        thread.start()
        return True, HTTPStatus.ACCEPTED, {"ok": True, "task_id": task_id, "status": "running"}

    def _run_task(self, task_id: str, payload: dict[str, Any]) -> None:
        task = self.tasks[task_id]
        try:
            module = self._load_module()
            fn = getattr(module, "execute_cleanup", None)
            if not callable(fn):
                raise RuntimeError("cleanup engine missing execute_cleanup(payload, log)")

            task.add_log("任务启动")
            summary = fn(payload, log=task.add_log)
            if not isinstance(summary, dict):
                raise RuntimeError("execute_cleanup() must return dict")
            task.summary = summary
            task.status = "completed"
            task.add_log("任务完成")
        except Exception as exc:
            task.status = "failed"
            task.error = str(exc)
            task.add_log(f"任务失败: {exc}")
            task.add_log(traceback.format_exc())
        finally:
            task.ended_at = time.time()
            with self.task_lock:
                if self.running_task_id == task_id:
                    self.running_task_id = None

    def task_snapshot(self, task_id: str) -> tuple[bool, int, dict[str, Any]]:
        task = self.tasks.get(task_id)
        if not task:
            return False, HTTPStatus.NOT_FOUND, {"ok": False, "error": "task not found"}

        payload = {
            "ok": True,
            "task_id": task.task_id,
            "status": task.status,
            "created_at": task.created_at,
            "started_at": task.started_at,
            "ended_at": task.ended_at,
            "logs": "\n".join(task.logs),
            "summary": task.summary,
            "error": task.error,
        }
        return True, HTTPStatus.OK, payload


class Handler(BaseHTTPRequestHandler):
    host: CleanupEngineHost
    html: str

    def _send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _send_html(self, html: str) -> None:
        raw = html.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _read_json(self) -> dict[str, Any]:
        size = int(self.headers.get("Content-Length", "0") or "0")
        if size <= 0:
            return {}
        raw = self.rfile.read(size)
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("JSON body must be an object")
        return data

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/":
            self._send_html(self.html)
            return

        if self.path == "/api/defaults":
            try:
                defaults = self.host.defaults()
                self._send_json({"ok": True, "defaults": defaults}, status=HTTPStatus.OK)
            except Exception as exc:
                self._send_json({"ok": False, "error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        if self.path.startswith("/api/tasks/"):
            task_id = self.path.split("/api/tasks/", 1)[1].strip()
            _, status, payload = self.host.task_snapshot(task_id)
            self._send_json(payload, status=status)
            return

        self._send_json({"ok": False, "error": "not found"}, status=HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/api/tasks":
            self._send_json({"ok": False, "error": "not found"}, status=HTTPStatus.NOT_FOUND)
            return

        try:
            payload = self._read_json()
        except Exception as exc:
            self._send_json({"ok": False, "error": f"invalid json: {exc}"}, status=HTTPStatus.BAD_REQUEST)
            return

        _, status, body = self.host.launch_task(payload)
        self._send_json(body, status=status)

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stdout.write("[HTTP] " + (fmt % args) + "\n")


def _load_html(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"missing html: {path}")
    return path.read_text(encoding="utf-8")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="CPA cleanup web ui")
    parser.add_argument("--host", default=os.getenv("CPA_WEB_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("CPA_WEB_PORT", "8123")))
    return parser.parse_args()


def run_server(host: str, port: int) -> None:
    handler = Handler
    handler.host = CleanupEngineHost(ENGINE_SCRIPT)
    handler.html = _load_html(INDEX_HTML)

    server = ThreadingHTTPServer((host, port), handler)
    print(f"[*] Web UI running: http://{host}:{port}")
    print(f"[*] Engine: {ENGINE_SCRIPT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[Info] stopped")
    finally:
        server.server_close()


def main() -> None:
    args = _parse_args()
    run_server(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
