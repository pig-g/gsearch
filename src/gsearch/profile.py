"""Profile lifecycle: state tracking, locking, and browser-install detection.

A fresh machine has no persistent Chromium profile and no Playwright browser
binary. This module handles the "first run" concerns that a plain search does
not: knowing whether setup has happened, preventing two concurrent runs from
clobbering the same profile directory, and detecting a missing browser.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, asdict
from typing import Optional

from .core import profile_dir, DEFAULT_PROFILE

# State file lives inside the profile directory so it travels with it.
STATE_FILENAME = "gsearch-state.json"

# How close to expiry we warn the user (seconds).
TRUST_STALE_SECONDS = 7 * 24 * 3600  # one week


@dataclass
class ProfileState:
    """Persisted setup/trust state for a profile directory."""

    initialized: bool = False
    created_at: float = 0.0
    last_trusted_at: float = 0.0
    last_blocked_at: float = 0.0
    consecutive_blocks: int = 0
    captcha_passes: int = 0
    version: int = 1

    @property
    def trusted(self) -> bool:
        return self.last_trusted_at > 0 and self.consecutive_blocks == 0

    @property
    def trust_age_seconds(self) -> float:
        if not self.last_trusted_at:
            return float("inf")
        return time.time() - self.last_trusted_at


def state_path(profile: Optional[str] = None) -> str:
    return os.path.join(profile or profile_dir(), STATE_FILENAME)


def load_state(profile: Optional[str] = None) -> ProfileState:
    path = state_path(profile)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        known = {k: v for k, v in data.items() if k in ProfileState.__dataclass_fields__}
        return ProfileState(**known)
    except (OSError, ValueError):
        return ProfileState()


def save_state(state: ProfileState, profile: Optional[str] = None) -> None:
    path = state_path(profile)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(asdict(state), fh, indent=2)
    os.replace(tmp, path)


def profile_exists(profile: Optional[str] = None) -> bool:
    """True if the profile directory looks like a real Chromium profile."""
    p = profile or profile_dir()
    # A real profile has a Default/ subdir or a Cookies DB after first launch.
    return os.path.isdir(p) and (
        os.path.isdir(os.path.join(p, "Default"))
        or os.path.exists(os.path.join(p, "Local State"))
        or os.path.exists(os.path.join(p, "Cookies"))
        or os.path.exists(os.path.join(p, "Default", "Cookies"))
    )


def mark_trusted(state: ProfileState) -> ProfileState:
    state.initialized = True
    if not state.created_at:
        state.created_at = time.time()
    state.last_trusted_at = time.time()
    state.consecutive_blocks = 0
    state.captcha_passes += 1
    return state


def mark_blocked(state: ProfileState) -> ProfileState:
    if not state.created_at:
        state.created_at = time.time()
    state.last_blocked_at = time.time()
    state.consecutive_blocks += 1
    return state


class ProfileLock:
    """A best-effort cross-process lock around a profile directory.

    Chromium itself refuses to start when a profile is already in use
    (SingletonLock). We create our own lock file first so concurrent gsearch
    runs fail with a friendly message instead of a Chromium crash.
    """

    def __init__(self, profile: Optional[str] = None, stale_after: int = 3600):
        self.profile = profile or profile_dir()
        self.lock_path = os.path.join(self.profile, ".gsearch.lock")
        self.stale_after = stale_after
        self._acquired = False

    def acquire(self) -> bool:
        os.makedirs(self.profile, exist_ok=True)
        # Reap a stale lock (crashed process) older than stale_after.
        try:
            if os.path.exists(self.lock_path):
                age = time.time() - os.path.getmtime(self.lock_path)
                if age > self.stale_after:
                    os.unlink(self.lock_path)
        except OSError:
            pass

        try:
            fd = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(fd, "w") as fh:
                fh.write(f"{os.getpid()}\n{int(time.time())}\n")
            self._acquired = True
            return True
        except FileExistsError:
            return False

    def holder_pid(self) -> Optional[int]:
        try:
            with open(self.lock_path, "r", encoding="utf-8") as fh:
                return int(fh.readline().strip())
        except (OSError, ValueError):
            return None

    def release(self) -> None:
        if self._acquired:
            try:
                os.unlink(self.lock_path)
            except OSError:
                pass
            self._acquired = False

    def __enter__(self) -> "ProfileLock":
        if not self.acquire():
            pid = self.holder_pid()
            where = f" (pid {pid})" if pid else ""
            raise RuntimeError(
                f"profile is already in use by another gsearch run{where}: {self.profile}\n"
                "wait for it to finish, or remove the lock file if it is stale:\n"
                f"  rm {self.lock_path}"
            )
        return self

    def __exit__(self, *exc) -> None:
        self.release()


def browser_installed() -> bool:
    """Check whether Playwright's Chromium binary is available."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return False
    try:
        with sync_playwright() as p:
            return os.path.exists(p.chromium.executable_path)
    except Exception:
        return False


def install_hint() -> str:
    return (
        "Playwright's Chromium browser is not installed.\n"
        "Install it with:\n"
        "    playwright install chromium\n"
        "or, if using the project venv:\n"
        "    ./.venv/bin/playwright install chromium"
    )