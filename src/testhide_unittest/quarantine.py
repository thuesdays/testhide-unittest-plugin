"""
Quarantine support: deselect/skip listed test ids before running.

The file lists one test id per line (the unittest id, e.g.
``tests.test_login.LoginTests.test_flaky``). Blank lines and ``#`` comments are ignored.
Discovery order: explicit path -> TESTHIDE_QUARANTINE_FILE env -> .testhide_quarantine_file
in the current dir.
"""
from __future__ import annotations

import os
import unittest
from typing import Optional, Set

_DEFAULT_NAME = ".testhide_quarantine_file"


def resolve_quarantine_path(explicit: Optional[str] = None) -> Optional[str]:
    if explicit:
        return explicit if os.path.isfile(explicit) else None
    env = os.environ.get("TESTHIDE_QUARANTINE_FILE")
    if env and os.path.isfile(env):
        return env
    if os.path.isfile(_DEFAULT_NAME):
        return _DEFAULT_NAME
    return None


def load_quarantine(path: Optional[str]) -> Set[str]:
    ids: Set[str] = set()
    if not path or not os.path.isfile(path):
        return ids
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line and not line.startswith("#"):
                    ids.add(line)
    except OSError:
        pass
    return ids


def filter_suite(suite: unittest.TestSuite, quarantined: Set[str]) -> unittest.TestSuite:
    """Return a new TestSuite with quarantined test ids removed (recursively)."""
    if not quarantined:
        return suite
    filtered = unittest.TestSuite()
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            filtered.addTest(filter_suite(item, quarantined))
        else:
            try:
                tid = item.id()
            except Exception:
                tid = None
            if tid not in quarantined:
                filtered.addTest(item)
    return filtered
