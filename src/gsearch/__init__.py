"""gsearch: Google search from the command line via a headed Playwright browser."""

from .core import search, build_url, resolve_redirect

__version__ = "0.1.0"
__all__ = ["search", "build_url", "resolve_redirect", "__version__"]