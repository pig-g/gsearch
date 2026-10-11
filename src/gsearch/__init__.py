"""gsearch: Google search from the command line via a headed Playwright browser."""

from .core import (
    search,
    build_url,
    resolve_redirect,
    check_trust,
    warmup,
    is_blocked,
    profile_dir,
)

__version__ = "0.2.0"
__all__ = [
    "search",
    "build_url",
    "resolve_redirect",
    "check_trust",
    "warmup",
    "is_blocked",
    "profile_dir",
    "__version__",
]