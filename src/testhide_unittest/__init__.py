"""
testhide-unittest-plugin — emit Testhide Report Format v1 from Python's ``unittest``.

Public API:
    TesthideTestRunner   — drop-in unittest runner that writes the report
    TesthideTestResult   — the underlying TestResult (advanced use)
    attach/set_info/set_jira/set_docstr — enrich the current test's report entry
    main                 — CLI entry (also ``python -m testhide_unittest``)
"""
from .runner import TesthideTestRunner, TesthideTestResult
from .context import attach, set_info, set_jira, set_docstr
from .report_core import SCHEMA_VERSION

__version__ = "0.1.0"

__all__ = [
    "TesthideTestRunner",
    "TesthideTestResult",
    "attach",
    "set_info",
    "set_jira",
    "set_docstr",
    "SCHEMA_VERSION",
    "main",
    "__version__",
]


def main(argv=None):
    from .cli import main as _main
    return _main(argv)
