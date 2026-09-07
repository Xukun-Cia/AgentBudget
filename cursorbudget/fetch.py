"""Load a sanitized usage snapshot via the shared Node status CLI."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional

FETCH_TIMEOUT_SEC = 90


@dataclass
class Snapshot:
    ok: bool
    error: Optional[str] = None
    fetch_error: Optional[str] = None
    remaining_days: Optional[float] = None
    api_percent: Optional[float] = None
    today_percent: Optional[float] = None
    today_cents: Optional[float] = None
    today_events: Optional[int] = None
    today_truncated: bool = False
    today_window_start: Optional[str] = None
    today_window_end: Optional[str] = None
    daily_budget: Optional[float] = None
    is_last_stretch: bool = False
    remaining_percent: Optional[float] = None
    membership_type: str = "unknown"
    api_used_cents: Optional[float] = None
    api_limit_cents: Optional[float] = None
    auto_percent: Optional[float] = None
    auto_used_cents: Optional[float] = None
    auto_limit_cents: Optional[float] = None
    included_used_cents: Optional[float] = None
    included_limit_cents: Optional[float] = None
    bonus_cents: Optional[float] = None
    cycle_start: Optional[str] = None
    cycle_end: Optional[str] = None
    workday_label: Optional[str] = None
    usage_source: Optional[str] = None
    gpt_ok: bool = False
    gpt_error: Optional[str] = None
    gpt_plan: Optional[str] = None
    gpt_percent: Optional[float] = None
    gpt_reset_at: Optional[str] = None
    gpt_window_seconds: Optional[float] = None
    gpt_allowed: Optional[bool] = None
    gpt_limit_reached: Optional[bool] = None
    gpt_cycle_start: Optional[str] = None
    gpt_cycle_end: Optional[str] = None
    gpt_source: Optional[str] = None
    gpt_windows: tuple = ()
    gpt_extras: tuple = ()


def lib_dir() -> Path:
    env = os.environ.get("CURSORBUDGET_LIB")
    if env:
        candidate = Path(env)
        if (candidate / "status-json.js").is_file():
            return candidate
    installed = Path("/usr/lib/cursorbudget/lib")
    if (installed / "status-json.js").is_file():
        return installed
    source = Path(__file__).resolve().parents[1] / "lib"
    if (source / "status-json.js").is_file():
        return source
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


def snapshot_from_dict(data: dict) -> Snapshot:
    return Snapshot(
        ok=bool(data.get("ok")),
        error=data.get("error") or None,
        fetch_error=data.get("fetchError") or None,
        remaining_days=_num(data.get("remainingDays")),
        api_percent=_num(data.get("apiPercent")),
        today_percent=_num(data.get("todayPercent")),
        today_cents=_num(data.get("todayCents")),
        today_events=_int(data.get("todayEvents")),
        today_truncated=bool(data.get("todayTruncated")),
        today_window_start=data.get("todayWindowStart") or None,
        today_window_end=data.get("todayWindowEnd") or None,
        daily_budget=_num(data.get("dailyBudget")),
        is_last_stretch=bool(data.get("isLastStretch")),
        remaining_percent=_num(data.get("remainingPercent")),
        membership_type=str(data.get("membershipType") or "unknown"),
        api_used_cents=_num(data.get("apiUsedCents")),
        api_limit_cents=_num(data.get("apiLimitCents")),
        auto_percent=_num(data.get("autoPercent")),
        auto_used_cents=_num(data.get("autoUsedCents")),
        auto_limit_cents=_num(data.get("autoLimitCents")),
        included_used_cents=_num(data.get("includedUsedCents")),
        included_limit_cents=_num(data.get("includedLimitCents")),
        bonus_cents=_num(data.get("bonusCents")),
        cycle_start=data.get("cycleStart") or None,
        cycle_end=data.get("cycleEnd") or None,
        workday_label=data.get("workdayLabel") or None,
        usage_source=data.get("usageSource") or None,
        gpt_ok=bool(data.get("gptOk")),
        gpt_error=data.get("gptError") or None,
        gpt_plan=data.get("gptPlan") or None,
        gpt_percent=_num(data.get("gptPercent")),
        gpt_reset_at=data.get("gptResetAt") or None,
        gpt_window_seconds=_num(data.get("gptWindowSeconds")),
        gpt_allowed=data.get("gptAllowed") if isinstance(data.get("gptAllowed"), bool) else None,
        gpt_limit_reached=data.get("gptLimitReached") if isinstance(data.get("gptLimitReached"), bool) else None,
        gpt_cycle_start=data.get("gptCycleStart") or None,
        gpt_cycle_end=data.get("gptCycleEnd") or None,
        gpt_source=data.get("gptSource") or None,
        gpt_windows=_gpt_rows(data.get("gptWindows")),
        gpt_extras=_extras(data.get("gptExtras")),
    )


def _extras(value) -> tuple:
    if not isinstance(value, list):
        return ()
    rows = []
    for item in value:
        if not isinstance(item, dict):
            continue
        label = item.get("label")
        pct = _num(item.get("percent"))
        if not label or pct is None:
            continue
        rows.append((str(label), pct))
    return tuple(rows)


def _gpt_rows(value) -> tuple:
    if not isinstance(value, list):
        return ()
    rows = []
    for item in value:
        if not isinstance(item, dict):
            continue
        label = item.get("label")
        pct = _num(item.get("percent"))
        if not label or pct is None:
            continue
        rows.append({
            "label": str(label),
            "group": str(item.get("group") or ""),
            "kind": str(item.get("kind") or ""),
            "percent": pct,
            "reset_at": item.get("resetAt") or None,
            "window_seconds": _num(item.get("windowSeconds")),
            "limit_reached": (
                item.get("limitReached")
                if isinstance(item.get("limitReached"), bool)
                else None
            ),
            "is_main": bool(item.get("isMain")),
        })
    return tuple(rows)


def fetch_snapshot() -> Snapshot:
    script = lib_dir() / "status-json.js"
    env = os.environ.copy()
    env.pop("CURSORBUDGET_DEBUG", None)
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
        err = (proc.stderr or "").strip() or f"status-json 无输出（exit {proc.returncode}）"
        return Snapshot(ok=False, error=err[:160])
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return Snapshot(ok=False, error="用量快照不是合法 JSON")
    if not isinstance(payload, dict):
        return Snapshot(ok=False, error="用量快照格式错误")
    return snapshot_from_dict(payload)
