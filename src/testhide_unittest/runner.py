"""
A drop-in unittest runner that emits Testhide Report Format v1 XML.

Usage (programmatic)::

    import unittest, testhide_unittest
    runner = testhide_unittest.TesthideTestRunner(report_path="junittests.xml")
    unittest.main(testRunner=runner)

or via the CLI (see __main__.py)::

    python -m testhide_unittest discover -s tests --report-xml junittests.xml
"""
from __future__ import annotations

import io
import sys
import time
import inspect
import traceback
import unittest
from typing import Dict, Optional

from . import context as _ctx
from .report_core import ReportWriter, TestCaseRecord, compute_fail_id
from .jira_helper import JiraHelper


class TesthideTestResult(unittest.TextTestResult):
    """TextTestResult that records each outcome as a Testhide report entry."""

    def __init__(self, stream, descriptions, verbosity,
                 writer: Optional[ReportWriter] = None,
                 capture_output: bool = True,
                 jira: Optional[JiraHelper] = None):
        super().__init__(stream, descriptions, verbosity)
        self._writer = writer
        self._capture = capture_output
        self._jira = jira
        self._start: Dict[int, float] = {}
        self._orig_out = None
        self._orig_err = None
        self._cap_out: Optional[io.StringIO] = None
        self._cap_err: Optional[io.StringIO] = None

    # --- timing + stdout capture -------------------------------------------------
    def startTest(self, test):
        super().startTest(test)
        self._start[id(test)] = time.perf_counter()
        _ctx._begin(test.id())
        if self._capture:
            self._orig_out, self._orig_err = sys.stdout, sys.stderr
            self._cap_out, self._cap_err = io.StringIO(), io.StringIO()
            sys.stdout, sys.stderr = self._cap_out, self._cap_err

    def _finish_capture(self) -> Optional[str]:
        if not self._capture or self._orig_out is None:
            return None
        sys.stdout, sys.stderr = self._orig_out, self._orig_err
        out = self._cap_out.getvalue() if self._cap_out else ""
        err = self._cap_err.getvalue() if self._cap_err else ""
        self._orig_out = self._orig_err = self._cap_out = self._cap_err = None
        combined = out + (("\n" + err) if err else "")
        return combined or None

    def _duration(self, test) -> float:
        t0 = self._start.pop(id(test), None)
        return (time.perf_counter() - t0) if t0 is not None else 0.0

    # --- metadata ----------------------------------------------------------------
    @staticmethod
    def _meta(test):
        cls = test.__class__
        module = cls.__module__ or ""
        classname = ("%s.%s" % (module, cls.__name__)) if module else cls.__name__
        method = getattr(cls, getattr(test, "_testMethodName", ""), None)
        file = ""
        line = ""
        try:
            file = inspect.getsourcefile(cls) or ""
        except Exception:
            pass
        try:
            if method is not None:
                _, ln = inspect.getsourcelines(method)
                line = str(ln)
        except Exception:
            pass
        docstr = None
        try:
            docstr = test.shortDescription() or (method.__doc__ if method else None)
        except Exception:
            pass
        return module, cls.__name__, classname, file, line, docstr

    def _base_record(self, test) -> TestCaseRecord:
        module, clsname, classname, file, line, docstr = self._meta(test)
        ctx = _ctx._end(test.id())
        return TestCaseRecord(
            classname=classname,
            name=getattr(test, "_testMethodName", str(test)),
            time=self._duration(test),
            file=file,
            line=line,
            docstr=ctx.get("docstr") or docstr,
            attachments=list(ctx.get("attachments") or []),
            info=ctx.get("info"),
            jira=ctx.get("jira"),
            system_out=self._finish_capture(),
        )

    @staticmethod
    def _exc_message(err) -> str:
        try:
            return str(err[1])
        except Exception:
            return ""

    @staticmethod
    def _format_tb(err) -> str:
        try:
            return "".join(traceback.format_exception(*err))
        except Exception:
            return ""

    def _apply_failure(self, rec: TestCaseRecord, test, err, *, outcome: str):
        module, clsname, *_ = self._meta(test)
        exc_type = err[0].__name__ if err and err[0] else "Error"
        msg = self._exc_message(err)
        rec.outcome = outcome
        rec.message = ("%s: %s" % (exc_type, msg)) if msg else exc_type
        rec.traceback = self._format_tb(err)
        rec.fail_id = compute_fail_id(module, clsname, rec.name, exc_type, msg)
        rec.test_resolution = "Teardown Error" if outcome == "error" else "Unresolved"
        if self._jira is not None and self._jira.available and rec.fail_id:
            enriched = self._jira.enrich(rec.fail_id)
            if enriched:
                rec.test_resolution, rec.jira, rec.message = enriched

    def _emit(self, rec: TestCaseRecord):
        if self._writer is not None:
            self._writer.write_case(rec)

    # --- outcome hooks -----------------------------------------------------------
    def addSuccess(self, test):
        super().addSuccess(test)
        rec = self._base_record(test)
        rec.outcome, rec.test_resolution, rec.fail_id = "passed", "Passed", ""
        self._emit(rec)

    def addFailure(self, test, err):
        super().addFailure(test, err)
        rec = self._base_record(test)
        self._apply_failure(rec, test, err, outcome="failed")
        self._emit(rec)

    def addError(self, test, err):
        super().addError(test, err)
        rec = self._base_record(test)
        self._apply_failure(rec, test, err, outcome="error")
        self._emit(rec)

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        rec = self._base_record(test)
        rec.outcome, rec.test_resolution = "skipped", "Skipped"
        rec.skip_reason = reason or ""
        self._emit(rec)

    def addExpectedFailure(self, test, err):
        super().addExpectedFailure(test, err)
        rec = self._base_record(test)
        module, clsname, *_ = self._meta(test)
        exc_type = err[0].__name__ if err and err[0] else "Error"
        msg = self._exc_message(err)
        rec.outcome = "xfail"
        rec.test_resolution = "Known Issue"
        rec.message = "Known Issue: %s" % (("%s: %s" % (exc_type, msg)) if msg else exc_type)
        rec.traceback = self._format_tb(err)
        rec.fail_id = compute_fail_id(module, clsname, rec.name, exc_type, msg)
        self._emit(rec)

    def addUnexpectedSuccess(self, test):
        super().addUnexpectedSuccess(test)
        # xpass: treat as a pass (the xfail marker should be removed), like the pytest plugin.
        rec = self._base_record(test)
        rec.outcome, rec.test_resolution, rec.fail_id = "passed", "Passed", ""
        self._emit(rec)


class TesthideTestRunner(unittest.TextTestRunner):
    """TextTestRunner that writes a Testhide v1 report on completion."""

    def __init__(self, report_path: str = "junittests.xml", suite_name: str = "unittest",
                 metadata: Optional[Dict[str, str]] = None, capture_output: bool = True,
                 jira: Optional[JiraHelper] = None, **kwargs):
        self._report_path = report_path
        self._suite_name = suite_name
        self._metadata = metadata or {}
        self._capture_output = capture_output
        self._jira = jira
        self._writer: Optional[ReportWriter] = None
        super().__init__(**kwargs)

    def _makeResult(self):
        return TesthideTestResult(
            self.stream, self.descriptions, self.verbosity,
            writer=self._writer, capture_output=self._capture_output, jira=self._jira,
        )

    def run(self, test):
        self._writer = ReportWriter(self._report_path, suite_name=self._suite_name, metadata=self._metadata)
        self._writer.start()
        try:
            return super().run(test)
        finally:
            self._writer.merge()
