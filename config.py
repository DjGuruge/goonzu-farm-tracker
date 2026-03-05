"""
Shared config — paths resolve correctly both from source and from a frozen .exe.
"""
import os
import sys


def _base_dir() -> str:
    """Directory next to the .exe when frozen, or CWD when running from source."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.getcwd()


def _resource_dir() -> str:
    """Where bundled read-only assets live (e.g. static/).
    In a frozen exe this is _MEIPASS; otherwise the project root."""
    if getattr(sys, "frozen", False):
        return sys._MEIPASS  # type: ignore[attr-defined]
    return os.path.dirname(os.path.abspath(__file__))


DB_NAME    = os.path.join(_base_dir(), "goonzu_farm.db")
STATIC_DIR = os.path.join(_resource_dir(), "static")
