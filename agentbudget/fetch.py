"""Load a sanitized usage snapshot via the shared Node status CLI."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional

FETCH_TIMEOUT_SEC = 90


@dataclass
class Snapshot:
    ok: bool
    error: Optional[str] = None
    fetch_error: Optional[str] = None
    api_percent: Optional[float] = None
    api_used_cents: Optional[float] = None
    api_limit_cents: Optional[float] = None
    auto_percent: Optional[float] = None
    auto_used_cents: Optional[float] = None
    auto_limit_cents: Optional[float] = None
    today_api_percent: Optional[float] = None
    today_api_cents: Optional[float] = None
    today_api_events: Optional[int] = None
    today_auto_percent: Optional[float] = None
    today_auto_cents: Optional[float] = None
    today_auto_events: Optional[int] = None
    today_truncated: bool = False
    today_window_start: Optional[str] = None
    today_window_end: Optional[str] = None
    cycle_start: Optional[str] = None
    cycle_end: Optional[str] = None
    gpt_ok: bool = False
    gpt_error: Optional[str] = None
    gpt_transient: bool = False
    gpt_stale: bool = False
    gpt_fetched_at: Optional[str] = None
    gpt_plan: Optional[str] = None
    gpt_percent: Optional[float] = None
    gpt_reset_at: Optional[str] = None
    gpt_limit_reached: Optional[bool] = None
    gpt_cycle_estimated: bool = False
    gpt_cycle_start: Optional[str] = None
    gpt_cycle_end: Optional[str] = None
    gpt_today_percent: Optional[float] = None
    gpt_today_partial: bool = False


def lib_dir() -> Path:
    env = os.environ.get("AGENTBUDGET_LIB")
    if env:
        candidate = Path(env)
        if (candidate / "status-json.js").is_file():
            return candidate
    source = Path(__file__).resolve().parents[1] / "lib"
    if (source / "status-json.js").is_file():
        return source
    installed = Path("/usr/lib/agentbudget/lib")
    if (installed / "status-json.js").is_file():
        return installed
    raise RuntimeError("找不到 status-json.js（请从源码运行或用 deb 安装）")


def _iter_node() -> Iterator[str]:
    # Prefer nvm first: Ubuntu's apt nodejs may be too old for desktop launch PATH.
    nvm = Path.home() / ".nvm" / "versions" / "node"
    if nvm.is_dir():
        for version in sorted(nvm.iterdir(), reverse=True):
            candidate = version / "bin" / "node"
            if candidate.is_file():
                yield str(candidate)
    for name in ("node", "nodejs"):
        found = shutil.which(name)
        if found:
            yield found
    for fallback in ("/usr/bin/nodejs", "/usr/bin/node"):
        if Path(fallback).is_file():
            yield fallback


def _node_major(path: str) -> Optional[int]:
    try:
        out = subprocess.check_output(
            [path, "-p", "process.versions.node.split('.')[0]"],
            text=True,
            timeout=5,
        ).strip()
        return int(out)
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def resolve_node() -> str:
    seen = set()
    candidates = []
    for path in _iter_node():
        if path in seen:
            continue
        seen.add(path)
        candidates.append(path)
        major = _node_major(path)
        if major is not None and major >= 12:
            return path
    if candidates:
        return candidates[0]
    raise RuntimeError("需要 Node.js 才能读取用量（apt 安装 nodejs，或保证 node 在 PATH 中）")


def _num(value) -> Optional[float]:
    if isinstance(value, (int, float)) and value == value:
        return float(value)
    return None


def _int(value) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value == int(value):
        return int(value)
    return None


def _bool_or_none(value) -> Optional[bool]:
    return value if isinstance(value, bool) else None


def snapshot_from_dict(data: dict) -> Snapshot:
    return Snapshot(
        ok=bool(data.get("ok")),
        error=data.get("error") or None,
        fetch_error=data.get("fetchError") or None,
        api_percent=_num(data.get("apiPercent")),
        api_used_cents=_num(data.get("apiUsedCents")),
        api_limit_cents=_num(data.get("apiLimitCents")),
        auto_percent=_num(data.get("autoPercent")),
        auto_used_cents=_num(data.get("autoUsedCents")),
        auto_limit_cents=_num(data.get("autoLimitCents")),
        today_api_percent=_num(data.get("todayApiPercent")),
        today_api_cents=_num(data.get("todayApiCents")),
        today_api_events=_int(data.get("todayApiEvents")),
        today_auto_percent=_num(data.get("todayAutoPercent")),
        today_auto_cents=_num(data.get("todayAutoCents")),
        today_auto_events=_int(data.get("todayAutoEvents")),
        today_truncated=bool(data.get("todayTruncated")),
        today_window_start=data.get("todayWindowStart") or None,
        today_window_end=data.get("todayWindowEnd") or None,
        cycle_start=data.get("cycleStart") or None,
        cycle_end=data.get("cycleEnd") or None,
        gpt_ok=bool(data.get("gptOk")),
        gpt_error=data.get("gptError") or None,
        gpt_transient=bool(data.get("gptTransient")),
        gpt_stale=bool(data.get("gptStale")),
        gpt_fetched_at=data.get("gptFetchedAt") or None,
        gpt_plan=data.get("gptPlan") or None,
        gpt_percent=_num(data.get("gptPercent")),
        gpt_reset_at=data.get("gptResetAt") or None,
        gpt_limit_reached=_bool_or_none(data.get("gptLimitReached")),
        gpt_cycle_estimated=bool(data.get("gptCycleEstimated")),
        gpt_cycle_start=data.get("gptCycleStart") or None,
        gpt_cycle_end=data.get("gptCycleEnd") or None,
        gpt_today_percent=_num(data.get("gptTodayPercent")),
        gpt_today_partial=bool(data.get("gptTodayPartial")),
    )


GPT_STALE_MAX_SEC = 15 * 60


def preserve_last_good_gpt(current: Snapshot, previous: Optional[Snapshot]) -> Snapshot:
    """Reuse a recent GPT value only for a transient failed refresh."""
    if current.gpt_ok and current.gpt_percent is not None:
        return replace(current, gpt_stale=False)
    if not current.gpt_transient or previous is None:
        return current
    if not previous.gpt_ok or previous.gpt_percent is None or not previous.gpt_fetched_at:
        return current
    try:
        fetched = datetime.fromisoformat(previous.gpt_fetched_at.replace("Z", "+00:00"))
        age = (datetime.now(timezone.utc) - fetched.astimezone(timezone.utc)).total_seconds()
    except (TypeError, ValueError):
        return current
    if age < 0 or age > GPT_STALE_MAX_SEC:
        return current

    values = {
        field: getattr(previous, field)
        for field in Snapshot.__dataclass_fields__
        if field.startswith("gpt_") and not field.startswith("gpt_today")
    }
    values.update({
        "gpt_ok": True,
        "gpt_error": current.gpt_error or "GPT 用量暂时刷新失败",
        "gpt_transient": True,
        "gpt_stale": True,
    })
    return replace(current, **values)


def fetch_snapshot() -> Snapshot:
    script = lib_dir() / "status-json.js"
    env = os.environ.copy()
    env.pop("AGENTBUDGET_DEBUG", None)
    try:
        proc = subprocess.run(
            [resolve_node(), str(script)],
            capture_output=True,
            text=True,
            timeout=FETCH_TIMEOUT_SEC,
            env=env,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return Snapshot(ok=False, error="读取用量超时")
    except RuntimeError as err:
        return Snapshot(ok=False, error=str(err))

    raw = (proc.stdout or "").strip()
    if not raw:
        return Snapshot(ok=False, error=f"用量读取失败（exit {proc.returncode}）")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return Snapshot(ok=False, error="用量快照不是合法 JSON")
    if not isinstance(payload, dict):
        return Snapshot(ok=False, error="用量快照格式错误")
    return snapshot_from_dict(payload)
