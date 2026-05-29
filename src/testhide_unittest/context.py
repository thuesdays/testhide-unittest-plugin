"""
Per-test context so test code can enrich its report entry, e.g.::

    import testhide_unittest as th

    class LoginTests(unittest.TestCase):
        def test_login(self):
            "User can log in."          # docstring -> docstr property (automatic)
            th.attach("/tmp/screenshot.png")
            th.set_info('{"env": "staging"}')
            ...

Data is keyed by the currently-running test (thread-local current id) and consumed by
TesthideTestResult when the test finishes. unittest runs tests sequentially in the main
thread by default, so this is safe; concurrent custom runners get per-thread isolation.
"""
from __future__ import annotations

import threading
from typing import Any, Dict, Optional

_local = threading.local()
_store: Dict[str, Dict[str, Any]] = {}
_lock = threading.Lock()


def _begin(test_id: str) -> None:
    _local.current = test_id
    with _lock:
        _store[test_id] = {"attachments": []}


def _end(test_id: str) -> Dict[str, Any]:
    _local.current = None
    with _lock:
        return _store.pop(test_id, {"attachments": []})


def _current() -> Optional[Dict[str, Any]]:
    tid = getattr(_local, "current", None)
    if tid is None:
        return None
    with _lock:
        return _store.get(tid)


def attach(path_or_url: str) -> None:
    """Attach a file path or URL (screenshot, log, json, …) to the current test."""
    d = _current()
    if d is not None and path_or_url:
        d["attachments"].append(str(path_or_url))


def set_info(info: Any) -> None:
    """Attach free-form context (JSON/text) to the current test."""
    d = _current()
    if d is not None and info is not None:
        d["info"] = str(info)


def set_jira(value: Any) -> None:
    """Attach a Jira reference to the current test."""
    d = _current()
    if d is not None and value:
        d["jira"] = str(value)


def set_docstr(value: Any) -> None:
    """Override the auto-captured docstring for the current test."""
    d = _current()
    if d is not None and value:
        d["docstr"] = str(value)
