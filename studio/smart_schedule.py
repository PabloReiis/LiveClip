"""Optional, local-only Instagram posting-window planner for LiveClipAI V2.

Does not use Instagram credentials or make network requests. It only selects a due_at
for a NEW queue item, leaving PeakCut's posting, retries, analytics and UI intact.
"""
from datetime import date, datetime, time as clock, timedelta, timezone
from pathlib import Path
from statistics import mean
import json
import math
import time

CONFIG_FILE = "instagram_horarios.json"
DEFAULTS = {
    "enabled": False,
    "instagram_account": "cortesgtavi3",
    "timezone": "America/Sao_Paulo",
    "windows": ["11:30", "12:30", "16:30", "18:30", "20:30", "22:00"],
    "initial_preferred": ["12:30", "18:30", "20:30"],
    "max_posts_per_day": 3,
    "minimum_gap_minutes": 120,
    "learn_from_views": True,
    "min_historical_posts": 12,
}


def _tz():
    # Windows may lack the IANA timezone database; 2026 Sao Paulo is UTC-03.
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo("America/Sao_Paulo")
    except Exception:
        return timezone(timedelta(hours=-3), name="America/Sao_Paulo (UTC-03 fallback)")


def cfg_path(data_dir):
    return Path(data_dir) / CONFIG_FILE


def load(data_dir):
    result = dict(DEFAULTS)
    f = cfg_path(data_dir)
    if f.is_file():
        try:
            raw = json.loads(f.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                result.update(raw)
        except (OSError, ValueError):
            pass
    result["instagram_account"] = str(result.get("instagram_account", "")).lstrip("@").lower()
    def valid_windows(windows):
        out = []
        if not isinstance(windows, list):
            return out
        for w in windows[:24]:
            if not isinstance(w, str) or len(w) != 5 or w[2] != ":":
                continue
            try:
                hh, mm = map(int, w.split(":"))
            except ValueError:
                continue
            if 0 <= hh <= 23 and 0 <= mm <= 59 and w not in out:
                out.append(w)
        return sorted(out)
    result["windows"] = valid_windows(result.get("windows")) or DEFAULTS["windows"]
    result["initial_preferred"] = [w for w in valid_windows(result.get("initial_preferred")) if w in result["windows"]] or DEFAULTS["initial_preferred"]
    result["max_posts_per_day"] = max(1, min(10, int(result.get("max_posts_per_day", 3))))
    result["minimum_gap_minutes"] = max(15, min(1440, int(result.get("minimum_gap_minutes", 120))))
    result["min_historical_posts"] = max(8, min(100, int(result.get("min_historical_posts", 12))))
    return result


def applies(account, data_dir):
    if not isinstance(account, dict) or account.get("platform") != "instagram":
        return False
    cfg = load(data_dir)
    if not cfg.get("enabled"):
        return False
    username = str(account.get("name", "")).strip().lstrip("@").lower()
    return bool(username and username == cfg["instagram_account"])


def _historical_scores(posts, windows, now, min_posts):
    """Heuristic using mature view totals; not follower-online analytics.

    Only historical posts older than 48h and less than 14d are considered.
    Nearby posts are assigned to the nearest configured slot if within 70 min.
    """
    tz = _tz()
    grouped = {w: [] for w in windows}
    usable = 0
    for p in posts:
        if p.get("status") != "posted":
            continue
        posted_at = p.get("posted_at")
        views = p.get("views")
        if not isinstance(posted_at, (int, float)) or not isinstance(views, (int, float)) or views < 0:
            continue
        age = now - posted_at
        if age < 48 * 3600 or age > 14 * 86400:
            continue
        local = datetime.fromtimestamp(posted_at, tz)
        minute = local.hour * 60 + local.minute
        nearest = min(windows, key=lambda x: abs(minute - 60*int(x[:2]) - int(x[3:])))
        delta = abs(minute - 60*int(nearest[:2]) - int(nearest[3:]))
        if delta <= 70:
            grouped[nearest].append(math.log1p(views))
            usable += 1
    if usable < min_posts or sum(bool(v) for v in grouped.values()) < 2:
        return None, usable
    global_mean = mean([x for values in grouped.values() for x in values])
    # Empirical-Bayes smoothing: a single viral post cannot dominate slots.
    scores = {w: ((sum(v) + 4 * global_mean) / (len(v) + 4)) for w, v in grouped.items()}
    return scores, usable


def preferred_windows(posts, cfg, now=None):
    now = time.time() if now is None else now
    windows = cfg["windows"]
    target_count = min(cfg["max_posts_per_day"], len(windows))
    priors = cfg["initial_preferred"]
    if not cfg.get("learn_from_views", True):
        return sorted(priors[:target_count]), 0, False
    scores, usable = _historical_scores(posts, windows, now, cfg["min_historical_posts"])
    if scores is None:
        return sorted(priors[:target_count]), usable, False
    # Small prior for baseline windows on sparse data; promote observed strong slots.
    ranked = sorted(windows, key=lambda w: (scores[w] + (0.08 if w in priors else 0.0), -int(w[:2]), -int(w[3:])), reverse=True)
    return sorted(ranked[:target_count]), usable, True


def next_slot(posts, gap_min, creator_daily_cap, data_dir, now=None):
    """Returns future Unix timestamp or None; preserves cap and spacing.

    Historical posts are provided only for the current user/account by posting.py.
    Existing scheduled posts remain untouched. 'now' (manual Post now) bypasses this planner.
    """
    cfg = load(data_dir)
    if not cfg["enabled"]:
        return None
    tz = _tz()
    now = time.time() if now is None else now
    effective_cap = min(int(creator_daily_cap), cfg["max_posts_per_day"])
    gap_sec = max(int(gap_min), cfg["minimum_gap_minutes"]) * 60
    booked = []
    for p in posts:
        if p.get("status") not in ("scheduled", "posting", "posted"):
            continue
        stamp = p.get("posted_at") or p.get("due_at")
        if isinstance(stamp, (int, float)) and stamp > 0:
            booked.append(float(stamp))
    earliest = max(now + 30, (max(booked) + gap_sec) if booked else now + 30)
    slots, _, _ = preferred_windows(posts, cfg, now)
    local_day = datetime.fromtimestamp(earliest, tz).date()
    for offset in range(90):
        this_day = local_day + timedelta(days=offset)
        scheduled_today = sum(datetime.fromtimestamp(t, tz).date() == this_day for t in booked)
        if scheduled_today >= effective_cap:
            continue
        for window in slots:
            hh, mm = map(int, window.split(":"))
            dt = datetime.combine(this_day, clock(hour=hh, minute=mm), tzinfo=tz)
            timestamp = dt.timestamp()
            if timestamp < earliest:
                continue
            if all(abs(timestamp - t) >= gap_sec for t in booked):
                return timestamp
    # Do not post immediately if no safe slot is found.
    raise RuntimeError("Nenhum horario disponivel dentro de 90 dias")
