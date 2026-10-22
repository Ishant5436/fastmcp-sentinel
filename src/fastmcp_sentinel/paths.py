"""Location of the native library and the audited C++ sources.

Resolution order (first match wins):

1. Explicit environment override (``SENTINEL_LIB_PATH`` / ``SENTINEL_CSRC_DIR``).
2. Inside the installed package (wheel builds ship both via scikit-build-core).
3. The ``csrc/`` directory of a source checkout (``make csrc`` / editable installs).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import List

_PACKAGE_DIR = Path(__file__).resolve().parent
_SOURCE_CSRC = _PACKAGE_DIR.parent.parent / "csrc"


def _lib_names() -> List[str]:
    if sys.platform == "darwin":
        return ["libsentinel_core.dylib"]
    if sys.platform == "win32":
        return ["sentinel_core.dll", "libsentinel_core.dll"]
    return ["libsentinel_core.so"]


def library_candidates() -> List[Path]:
    env = os.environ.get("SENTINEL_LIB_PATH")
    if env:
        return [Path(env)]
    dirs = [_PACKAGE_DIR, _SOURCE_CSRC]
    return [d / name for d in dirs for name in _lib_names()]


def find_library() -> Path:
    candidates = library_candidates()
    for path in candidates:
        if path.is_file():
            return path
    searched = ", ".join(str(p) for p in candidates)
    raise FileNotFoundError(
        f"Native sentinel_core library not found (searched: {searched}). "
        "Build it with `make csrc`, install the package with `pip install .`, "
        "or set SENTINEL_LIB_PATH."
    )


def find_csrc_dir() -> Path:
    env = os.environ.get("SENTINEL_CSRC_DIR")
    if env:
        return Path(env)
    for candidate in (_PACKAGE_DIR / "csrc", _SOURCE_CSRC):
        if (candidate / "sentinel_core.cpp").is_file():
            return candidate
    return _SOURCE_CSRC
