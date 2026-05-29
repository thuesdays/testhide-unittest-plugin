"""
CLI: a thin wrapper over ``unittest`` that injects the Testhide runner.

    python -m testhide_unittest discover -s tests --report-xml junittests.xml
    python -m testhide_unittest tests.test_login --report-xml junittests.xml

Testhide options (consumed here, everything else is passed straight to unittest):
    --report-xml PATH        output report path (default: junittests.xml)
    --suite-name NAME        <testsuite name="..."> (default: unittest)
    --quarantine-file PATH   deselect listed test ids (env TESTHIDE_QUARANTINE_FILE / .testhide_quarantine_file)
    --no-capture             do not capture stdout/stderr into <system-out>
    --meta KEY=VALUE         add a suite <property> (repeatable)
    --jira-url / --jira-username / --jira-password   optional Jira enrichment
"""
from __future__ import annotations

import sys
import unittest
from typing import List, Optional

from .runner import TesthideTestRunner
from .quarantine import resolve_quarantine_path, load_quarantine, filter_suite
from .jira_helper import JiraHelper


def _extract_opt(argv: List[str], name: str, has_value: bool = True):
    """
    Remove and return the FIRST ``--name value`` / ``--name=value`` from argv.
    Returns the value (str), or True for a flag, or None if absent. Removing only the
    first occurrence lets _extract_multi collect repeated options one at a time.
    """
    i = 0
    while i < len(argv):
        tok = argv[i]
        if tok == name:
            if has_value:
                val = argv[i + 1] if i + 1 < len(argv) else None
                del argv[i:i + 2]
                return val
            del argv[i]
            return True
        if has_value and tok.startswith(name + "="):
            val = tok.split("=", 1)[1]
            del argv[i]
            return val
        i += 1
    return None


def _extract_multi(argv: List[str], name: str) -> List[str]:
    vals: List[str] = []
    while True:
        v = _extract_opt(argv, name, has_value=True)
        if v is None:
            break
        vals.append(v)
    return vals


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    prog = argv[0]
    rest = argv[1:]

    report_path = _extract_opt(rest, "--report-xml") or "junittests.xml"
    suite_name = _extract_opt(rest, "--suite-name") or "unittest"
    quarantine_arg = _extract_opt(rest, "--quarantine-file")
    no_capture = _extract_opt(rest, "--no-capture", has_value=False) is True
    metas = _extract_multi(rest, "--meta")
    jira_url = _extract_opt(rest, "--jira-url")
    jira_user = _extract_opt(rest, "--jira-username")
    jira_pass = _extract_opt(rest, "--jira-password")

    metadata = {}
    for m in metas:
        if "=" in m:
            k, v = m.split("=", 1)
            metadata[k.strip()] = v.strip()

    jira = None
    if jira_url and jira_user and jira_pass:
        jira = JiraHelper(jira_url, jira_user, jira_pass)

    runner = TesthideTestRunner(
        report_path=report_path,
        suite_name=suite_name,
        metadata=metadata,
        capture_output=not no_capture,
        jira=jira,
    )

    quarantine_ids = load_quarantine(resolve_quarantine_path(quarantine_arg))

    # unittest.TestProgram runs createTests() (and the tests) inside __init__, so the
    # quarantine filter must be applied from within createTests — capture ids via closure.
    class _Program(unittest.TestProgram):
        def createTests(self, *args, **kwargs):
            super().createTests(*args, **kwargs)
            if quarantine_ids and self.test is not None:
                self.test = filter_suite(self.test, quarantine_ids)

    program = _Program(
        module=None,
        argv=[prog] + rest,
        testRunner=runner,
        exit=False,
    )
    result = program.result
    return 0 if (result is not None and result.wasSuccessful()) else 1


if __name__ == "__main__":
    sys.exit(main())
