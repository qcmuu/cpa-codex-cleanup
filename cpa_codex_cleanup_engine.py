
#!/usr/bin/env python3
"""cpa-codex-cleanup engine (rewritten).

Main public API for other modules:
- web_defaults() -> dict
- execute_cleanup(payload: dict, log: callable | None = None) -> dict
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Optional
from urllib.parse import urlparse, urlunparse

from curl_cffi import requests


STATUS_KEYWORDS = {
    "token_invalidated",
    "token_revoked",
    "usage_limit_reached",
}

MESSAGE_KEYWORDS = [
    "额度获取失败：401",
    '"status":401',
    '"status": 401',
    "your authentication token has been invalidated.",
    "encountered invalidated oauth token for user",
    "token_invalidated",
    "token_revoked",
    "usage_limit_reached",
]

PROBE_TARGET_URL = "https://chatgpt.com/backend-api/codex/responses/compact"
PROBE_MODEL = "gpt-5.1-codex"


def normalize_api_root(raw_url: str) -> str:
    value = (raw_url or "").strip()
    if not value:
        return ""

    parsed = urlparse(value)
    path = parsed.path or ""

    if path.endswith("/management.html"):
        path = path[: -len("/management.html")] + "/v0/management"

    for suffix in ("/api-call", "/auth-files"):
        if path.endswith(suffix):
            path = path[: -len(suffix)]

    normalized = urlunparse((parsed.scheme, parsed.netloc, path.rstrip("/"), "", "", ""))
    return normalized.rstrip("/")


@dataclass(frozen=True)
class CleanupConfig:
    management_url: str
    management_token: str
    management_timeout: int = 15
    active_probe: bool = True
    probe_timeout: int = 8
    probe_workers: int = 12
    delete_workers: int = 8
    max_active_probes: int = 120

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "CleanupConfig":
        def to_int(name: str, default: int, minimum: int) -> int:
            try:
                parsed = int(data.get(name, default))
            except Exception:
                parsed = default
            return max(minimum, parsed)

        def to_bool(name: str, default: bool) -> bool:
            raw = data.get(name, default)
            if isinstance(raw, bool):
                return raw
            text = str(raw).strip().lower()
            if text in {"1", "true", "yes", "on"}:
                return True
            if text in {"0", "false", "no", "off"}:
                return False
            return default

        return cls(
            management_url=normalize_api_root(str(data.get("management_url", "") or "")),
            management_token=str(data.get("management_token", "") or "").strip(),
            management_timeout=to_int("management_timeout", 15, 1),
            active_probe=to_bool("active_probe", True),
            probe_timeout=to_int("probe_timeout", 8, 1),
            probe_workers=to_int("probe_workers", 12, 1),
            delete_workers=to_int("delete_workers", 8, 1),
            max_active_probes=to_int("max_active_probes", 120, 0),
        )

    def validate(self) -> tuple[bool, str]:
        if not self.management_url:
            return False, "management_url 不能为空"
        if not self.management_token:
            return False, "management_token 不能为空"
        if not self.management_url.startswith(("http://", "https://")):
            return False, "management_url 必须以 http:// 或 https:// 开头"
        return True, ""

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "management_url": self.management_url,
            "management_token": self.management_token,
            "management_timeout": self.management_timeout,
            "active_probe": self.active_probe,
            "probe_timeout": self.probe_timeout,
            "probe_workers": self.probe_workers,
            "delete_workers": self.delete_workers,
            "max_active_probes": self.max_active_probes,
        }


@dataclass(frozen=True)
class CleanupHit:
    name: str
    keyword: str
    status_message: str


@dataclass(frozen=True)
class CleanupReport:
    scanned_total: int
    matched_total: int
    deleted_main: int
    deleted_401: int
    deleted_total: int
    failures: list[dict[str, str]]
    matched: list[dict[str, str]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "scanned_total": self.scanned_total,
            "matched_total": self.matched_total,
            "deleted_main": self.deleted_main,
            "deleted_401": self.deleted_401,
            "deleted_total": self.deleted_total,
            "failures": self.failures,
            "matched": self.matched,
        }


class ManagementGateway:
    def __init__(self, config: CleanupConfig):
        self.config = config

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.config.management_token}"}

    @property
    def auth_files_endpoint(self) -> str:
        return self.config.management_url.rstrip("/") + "/auth-files"

    @property
    def api_call_endpoint(self) -> str:
        return self.config.management_url.rstrip("/") + "/api-call"

    def list_auth_files(self) -> list[dict[str, Any]]:
        resp = requests.get(self.auth_files_endpoint, headers=self._headers, timeout=self.config.management_timeout)
        if resp.status_code == 404:
            raise RuntimeError(
                f"auth-files 接口不存在: {self.auth_files_endpoint} (HTTP 404). "
                "请确认 management_url 是管理 API 根路径，如 .../v0/management"
            )
        resp.raise_for_status()
        payload = resp.json()
        files = payload.get("files", []) if isinstance(payload, dict) else []
        return files if isinstance(files, list) else []

    def delete_auth_file(self, name: str) -> tuple[bool, str]:
        resp = requests.delete(
            self.auth_files_endpoint,
            params={"name": name},
            headers=self._headers,
            timeout=self.config.management_timeout,
        )
        if 200 <= resp.status_code < 300:
            return True, ""

        detail = ""
        try:
            detail = json.dumps(resp.json(), ensure_ascii=False)
        except Exception:
            detail = resp.text
        return False, f"HTTP {resp.status_code}: {detail}"

    def probe_auth_index(self, auth_index: str) -> tuple[int, str]:
        payload = {
            "auth_index": auth_index,
            "method": "POST",
            "url": PROBE_TARGET_URL,
            "header": {
                "Authorization": "Bearer $TOKEN$",
                "Content-Type": "application/json",
                "User-Agent": "codex_cli_rs/0.101.0",
            },
            "data": json.dumps(
                {
                    "model": PROBE_MODEL,
                    "input": [{"role": "user", "content": "ping"}],
                },
                ensure_ascii=False,
            ),
        }
        resp = requests.post(
            self.api_call_endpoint,
            headers=self._headers,
            json=payload,
            timeout=self.config.probe_timeout,
        )
        resp.raise_for_status()
        body = resp.json()
        if not isinstance(body, dict):
            return 0, ""
        return int(body.get("status_code", 0) or 0), str(body.get("body", "") or "")


def _now() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _safe_status_message(file_obj: dict[str, Any]) -> str:
    return str(file_obj.get("status_message", "") or "")


def _reason_from_status(file_obj: dict[str, Any]) -> str:
    status_message = _safe_status_message(file_obj)
    if not status_message:
        return ""

    lower_msg = status_message.lower()
    for keyword in MESSAGE_KEYWORDS:
        if keyword in lower_msg:
            return keyword

    try:
        parsed = json.loads(status_message)
    except Exception:
        parsed = None

    if isinstance(parsed, dict):
        if int(parsed.get("status", 0) or 0) == 401:
            return "status_401"
        err = parsed.get("error", {})
        if isinstance(err, dict):
            code = str(err.get("code", "") or "")
            if code in STATUS_KEYWORDS:
                return code

    return ""


def _looks_401(file_obj: dict[str, Any]) -> bool:
    try:
        if int(file_obj.get("status", 0) or 0) == 401:
            return True
    except Exception:
        pass
    text = _safe_status_message(file_obj).lower()
    return "401" in text or "unauthorized" in text


class CleanupOrchestrator:
    def __init__(self, config: CleanupConfig, log: Optional[Callable[[str], None]] = None):
        self.config = config
        self.gateway = ManagementGateway(config)
        self.log = log or (lambda msg: None)

    def _log(self, message: str) -> None:
        self.log(message)

    def _probe_one(self, file_obj: dict[str, Any]) -> tuple[str, str]:
        name = str(file_obj.get("name", "") or "")
        auth_index = str(file_obj.get("auth_index", "") or "").strip()
        if not auth_index:
            return name, ""

        try:
            status_code, body = self.gateway.probe_auth_index(auth_index)
        except Exception as exc:
            return name, f"probe_error:{exc}"

        body_lower = body.lower()
        if status_code == 401:
            return name, "probe_status_401"
        if "401" in body_lower or "unauthorized" in body_lower:
            return name, "probe_body_401"

        for keyword in MESSAGE_KEYWORDS:
            if keyword in body_lower:
                return name, f"probe_{keyword}"

        return name, ""

    def _delete_batch(self, hits: list[CleanupHit]) -> tuple[int, list[dict[str, str]]]:
        deleted = 0
        failures: list[dict[str, str]] = []
        total = len(hits)

        def task(item: CleanupHit) -> tuple[str, bool, str]:
            ok, err = self.gateway.delete_auth_file(item.name)
            return item.name, ok, err

        with ThreadPoolExecutor(max_workers=self.config.delete_workers) as pool:
            future_map: dict[Future[tuple[str, bool, str]], CleanupHit] = {
                pool.submit(task, item): item for item in hits
            }
            done = 0
            for future in as_completed(future_map):
                done += 1
                name, ok, err = future.result()
                if ok:
                    deleted += 1
                    self._log(f"[{_now()}] 删除成功: {name} ({done}/{total})")
                else:
                    failures.append({"name": name, "error": err})
                    self._log(f"[{_now()}] 删除失败: {name} -> {err}")

        return deleted, failures

    def _cleanup_401_only(self, exclude_names: set[str]) -> tuple[int, list[dict[str, str]]]:
        try:
            files = self.gateway.list_auth_files()
        except Exception as exc:
            self._log(f"[{_now()}] 401补删列表读取失败: {exc}")
            return 0, [{"name": "<list>", "error": str(exc)}]

        targets: list[CleanupHit] = []
        for file_obj in files:
            name = str(file_obj.get("name", "") or "")
            if not name or name in exclude_names:
                continue
            if _looks_401(file_obj):
                targets.append(CleanupHit(name=name, keyword="status_401", status_message=_safe_status_message(file_obj)))

        if not targets:
            self._log(f"[{_now()}] 401补删: 无目标")
            return 0, []

        self._log(f"[{_now()}] 401补删: 待删除 {len(targets)} 个")
        deleted, failures = self._delete_batch(targets)
        return deleted, failures

    def run(self) -> CleanupReport:
        self._log(f"[{_now()}] 开始清理")
        self._log(f"[{_now()}] 配置: active_probe={self.config.active_probe}, probe_workers={self.config.probe_workers}, delete_workers={self.config.delete_workers}, max_active_probes={self.config.max_active_probes}")

        files = self.gateway.list_auth_files()
        self._log(f"[{_now()}] 拉取 auth-files 成功，总数: {len(files)}")

        fixed_hits: list[CleanupHit] = []
        probe_candidates: list[dict[str, Any]] = []

        for file_obj in files:
            reason = _reason_from_status(file_obj)
            name = str(file_obj.get("name", "") or "")
            if not name:
                continue
            if reason:
                fixed_hits.append(CleanupHit(name=name, keyword=reason, status_message=_safe_status_message(file_obj)))
                continue

            provider = str(file_obj.get("provider", "") or "").strip().lower()
            auth_index = str(file_obj.get("auth_index", "") or "").strip()
            if self.config.active_probe and provider == "codex" and auth_index:
                probe_candidates.append(file_obj)

        if self.config.active_probe and self.config.max_active_probes > 0 and len(probe_candidates) > self.config.max_active_probes:
            self._log(f"[{_now()}] 主动探测候选 {len(probe_candidates)}，仅探测前 {self.config.max_active_probes} 个")
            probe_candidates = probe_candidates[: self.config.max_active_probes]

        probed_hits: list[CleanupHit] = []
        if self.config.active_probe and self.config.max_active_probes != 0 and probe_candidates:
            self._log(f"[{_now()}] 开始主动探测，候选 {len(probe_candidates)} 个")
            with ThreadPoolExecutor(max_workers=self.config.probe_workers) as pool:
                future_map: dict[Future[tuple[str, str]], dict[str, Any]] = {
                    pool.submit(self._probe_one, item): item for item in probe_candidates
                }
                done = 0
                total = len(probe_candidates)
                for future in as_completed(future_map):
                    done += 1
                    name, reason = future.result()
                    if reason:
                        if not reason.startswith("probe_error"):
                            status_message = _safe_status_message(future_map[future])
                            probed_hits.append(CleanupHit(name=name, keyword=reason, status_message=status_message))
                            self._log(f"[{_now()}] 探测命中: {name} -> {reason}")
                        else:
                            self._log(f"[{_now()}] 探测异常: {name} -> {reason}")

                    if done % 20 == 0 or done == total:
                        self._log(f"[{_now()}] 探测进度: {done}/{total}")
        else:
            self._log(f"[{_now()}] 主动探测已关闭或无候选")

        merged_by_name: dict[str, CleanupHit] = {}
        for item in fixed_hits + probed_hits:
            if item.name not in merged_by_name:
                merged_by_name[item.name] = item

        matched = list(merged_by_name.values())
        self._log(f"[{_now()}] 命中删除规则: {len(matched)}")

        deleted_main = 0
        failures: list[dict[str, str]] = []
        if matched:
            deleted_main, failures = self._delete_batch(matched)
        else:
            self._log(f"[{_now()}] 主流程无删除目标")

        deleted_401, failures_401 = self._cleanup_401_only(set(merged_by_name.keys()))
        failures.extend(failures_401)

        report = CleanupReport(
            scanned_total=len(files),
            matched_total=len(matched),
            deleted_main=deleted_main,
            deleted_401=deleted_401,
            deleted_total=deleted_main + deleted_401,
            failures=failures,
            matched=[
                {
                    "name": item.name,
                    "keyword": item.keyword,
                    "status_message": item.status_message,
                }
                for item in matched
            ],
        )

        self._log(f"[{_now()}] 完成: scanned={report.scanned_total}, matched={report.matched_total}, deleted_main={report.deleted_main}, deleted_401={report.deleted_401}, deleted_total={report.deleted_total}")
        if report.failures:
            self._log(f"[{_now()}] 失败数: {len(report.failures)}")
        return report


def web_defaults() -> dict[str, Any]:
    config = CleanupConfig(
        management_url=os.getenv("CPA_MANAGEMENT_URL", "http://127.0.0.1:8317/management.html"),
        management_token=os.getenv("CPA_MANAGEMENT_TOKEN", "management_token"),
        management_timeout=max(1, int(os.getenv("MANAGEMENT_TIMEOUT_SECONDS", "15") or "15")),
        active_probe=str(os.getenv("ACTIVE_PROBE", "1")).strip().lower() not in {"0", "false", "no", "off"},
        probe_timeout=max(1, int(os.getenv("PROBE_TIMEOUT_SECONDS", "8") or "8")),
        probe_workers=max(1, int(os.getenv("PROBE_WORKERS", "12") or "12")),
        delete_workers=max(1, int(os.getenv("DELETE_WORKERS", "8") or "8")),
        max_active_probes=max(0, int(os.getenv("MAX_ACTIVE_PROBES", "120") or "120")),
    )
    return config.to_public_dict()


def execute_cleanup(payload: dict[str, Any], log: Optional[Callable[[str], None]] = None) -> dict[str, Any]:
    config = CleanupConfig.from_mapping(payload)
    ok, msg = config.validate()
    if not ok:
        raise ValueError(msg)

    orchestrator = CleanupOrchestrator(config=config, log=log)
    return orchestrator.run().to_dict()


def _parse_cli_args() -> argparse.Namespace:
    d = web_defaults()
    parser = argparse.ArgumentParser(description="cpa-codex-cleanup engine")
    parser.add_argument("--management-url", default=d["management_url"], help="管理 API 根路径")
    parser.add_argument("--management-token", default=d["management_token"], help="管理 Token")
    parser.add_argument("--management-timeout", type=int, default=d["management_timeout"], help="管理接口超时(秒)")
    parser.add_argument("--active-probe", dest="active_probe", action="store_true", default=d["active_probe"], help="开启主动探测")
    parser.add_argument("--no-active-probe", dest="active_probe", action="store_false", help="关闭主动探测")
    parser.add_argument("--probe-timeout", type=int, default=d["probe_timeout"], help="探测超时(秒)")
    parser.add_argument("--probe-workers", type=int, default=d["probe_workers"], help="探测并发")
    parser.add_argument("--delete-workers", type=int, default=d["delete_workers"], help="删除并发")
    parser.add_argument("--max-active-probes", type=int, default=d["max_active_probes"], help="最大探测数量")
    parser.add_argument("--json", action="store_true", help="以 JSON 打印结果")
    return parser.parse_args()


def main() -> None:
    args = _parse_cli_args()
    payload = {
        "management_url": args.management_url,
        "management_token": args.management_token,
        "management_timeout": args.management_timeout,
        "active_probe": args.active_probe,
        "probe_timeout": args.probe_timeout,
        "probe_workers": args.probe_workers,
        "delete_workers": args.delete_workers,
        "max_active_probes": args.max_active_probes,
    }

    def log_line(msg: str) -> None:
        print(msg, flush=True)

    try:
        result = execute_cleanup(payload, log=log_line)
    except Exception as exc:
        print(f"[Error] {exc}", file=sys.stderr, flush=True)
        raise SystemExit(1)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
