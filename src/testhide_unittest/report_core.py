"""
Self-contained writer for the **Testhide Report Format v1**.

Produces the JUnit-extended dialect the Testhide C# agent parses
(see testhide/docs/specs/REPORT-FORMAT-V1.md). Has no third-party dependencies so it
can be vendored into any Python plugin. Mirrors the contract emitted by
testhide-pytest-plugin (same fail_id formula, same testsuite/testcase/properties layout),
and additionally emits the ``testhide_schema_version`` suite property.
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import socket
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

SCHEMA_VERSION = "1"

_PARAM_SUFFIX = re.compile(r"\[.+\]$")


def compute_fail_id(module: str, cls: str, func: str, exc_type: str, message: str) -> str:
    """md5("module.class.function.ExceptionType(message)") — identical to the pytest plugin."""
    func = _PARAM_SUFFIX.sub("", func or "")
    raw = "%s.%s.%s.%s(%s)" % (module or "", cls or module or "", func, exc_type or "", message or "")
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def _hostname() -> str:
    try:
        return socket.gethostname()
    except Exception:
        return "unknown"


def _ip() -> str:
    try:
        return socket.gethostbyname(socket.gethostname())
    except Exception:
        return "0.0.0.0"


@dataclass
class TestCaseRecord:
    classname: str
    name: str
    time: float
    # one of: passed | failed | error | skipped | xfail
    outcome: str = "passed"
    file: str = ""
    line: str = ""
    fail_id: str = ""
    test_resolution: str = "Unresolved"
    message: str = ""
    traceback: str = ""
    skip_reason: str = ""
    docstr: Optional[str] = None
    info: Optional[str] = None
    jira: Optional[str] = None
    attachments: List[str] = field(default_factory=list)
    system_out: Optional[str] = None


def build_testcase_element(rec: TestCaseRecord) -> ET.Element:
    """Serialize one TestCaseRecord into a <testcase> element per the v1 contract."""
    tc = ET.Element(
        "testcase",
        {
            "classname": rec.classname or "",
            "name": rec.name or "",
            "file": rec.file or "",
            "line": str(rec.line or ""),
            "time": "%.3f" % float(rec.time or 0.0),
            "fail_id": rec.fail_id or "",
            "test_resolution": rec.test_resolution or "Unresolved",
        },
    )

    if rec.outcome in ("failed", "xfail"):
        # xfail (expected failure that did fail) is emitted as <failure> with
        # test_resolution="Known Issue" — matches the spec and the pytest plugin.
        fe = ET.SubElement(tc, "failure", message=rec.message or "")
        if rec.traceback:
            fe.text = rec.traceback
    elif rec.outcome == "error":
        ee = ET.SubElement(tc, "error", message=rec.message or "")
        if rec.traceback:
            ee.text = rec.traceback
    elif rec.outcome == "skipped":
        se = ET.SubElement(tc, "skipped", type="skip", message=rec.skip_reason or rec.message or "")
        txt = rec.traceback or rec.skip_reason
        if txt:
            se.text = txt

    properties: List[tuple] = []
    if rec.docstr:
        properties.append(("docstr", rec.docstr))
    for att in rec.attachments:
        if att:
            properties.append(("attachment", att))
    if rec.info:
        properties.append(("info", rec.info))
    if rec.jira:
        properties.append(("jira", rec.jira))
    if properties:
        pe = ET.SubElement(tc, "properties")
        for name, value in properties:
            ET.SubElement(pe, "property", name=str(name), value=str(value))

    if rec.system_out:
        so = ET.SubElement(tc, "system-out")
        so.text = rec.system_out

    return tc


class FileLock:
    """Best-effort cross-process lock so parallel writers can't corrupt the final report."""

    def __init__(self, path: str, timeout: float = 15.0):
        self.path = path
        self.timeout = timeout
        self.fd: Optional[int] = None

    def __enter__(self):
        start = time.time()
        while True:
            try:
                self.fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_RDWR)
                return self
            except FileExistsError:
                if time.time() - start > self.timeout:
                    # stale lock — steal it
                    try:
                        os.remove(self.path)
                    except OSError:
                        pass
                    continue
                time.sleep(0.05)
            except OSError:
                # filesystem can't honor O_EXCL — proceed lock-free rather than hang
                return self

    def __exit__(self, *exc):
        try:
            if self.fd is not None:
                os.close(self.fd)
            os.remove(self.path)
        except OSError:
            pass


class ReportWriter:
    """
    Collects per-test XML chunks under a temp dir and atomically merges them into the
    final report on ``merge()``. Parallel/sharded safe (each chunk is a separate file,
    keyed by sequence + pid; merge is file-locked).
    """

    def __init__(self, report_path: str, suite_name: str = "unittest",
                 metadata: Optional[Dict[str, str]] = None):
        self.report_path = os.path.abspath(report_path)
        self.suite_name = suite_name
        self.metadata = dict(metadata or {})
        self.temp_dir = self._temp_dir_for(self.report_path)
        self._seq = 0
        self._merged = False

    @staticmethod
    def _temp_dir_for(path: str) -> str:
        d = os.path.dirname(path) or "."
        return os.path.join(d, ".%s_temp" % os.path.basename(path))

    def start(self) -> None:
        if os.path.isdir(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        os.makedirs(self.temp_dir, exist_ok=True)

    def write_case(self, rec: TestCaseRecord) -> None:
        os.makedirs(self.temp_dir, exist_ok=True)
        self._seq += 1
        fname = os.path.join(self.temp_dir, "case_%06d_%d.xml" % (self._seq, os.getpid()))
        ET.ElementTree(build_testcase_element(rec)).write(fname, encoding="utf-8", xml_declaration=True)

    def merge(self) -> None:
        if self._merged:
            return
        self._merged = True

        with FileLock(self.report_path + ".lock"):
            root = ET.Element("testsuites")
            suite = ET.SubElement(
                root, "testsuite",
                name=self.suite_name,
                timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
                hostname=_hostname(),
            )
            props = ET.SubElement(suite, "properties")
            ET.SubElement(props, "property", name="testhide_schema_version", value=SCHEMA_VERSION)
            ET.SubElement(props, "property", name="ip_address", value=_ip())
            ET.SubElement(props, "property", name="hostname", value=_hostname())
            for k, v in self.metadata.items():
                ET.SubElement(props, "property", name=str(k), value=str(v))

            if os.path.isdir(self.temp_dir):
                for fname in sorted(os.listdir(self.temp_dir)):
                    if fname.endswith(".xml"):
                        try:
                            suite.append(ET.parse(os.path.join(self.temp_dir, fname)).getroot())
                        except ET.ParseError:
                            continue

            cases = suite.findall("testcase")
            suite.set("tests", str(len(cases)))
            suite.set("failures", str(len(suite.findall(".//failure"))))
            suite.set("errors", str(len(suite.findall(".//error"))))
            suite.set("skipped", str(len(suite.findall(".//skipped"))))
            suite.set("time", "%.3f" % sum(float(c.get("time", 0) or 0) for c in cases))

            try:
                ET.indent(ET.ElementTree(root), space="\t")  # Python 3.9+ (best effort)
            except Exception:
                pass

            os.makedirs(os.path.dirname(self.report_path) or ".", exist_ok=True)
            tmp = self.report_path + ".tmp"
            ET.ElementTree(root).write(tmp, encoding="utf-8", xml_declaration=True)
            os.replace(tmp, self.report_path)

        if os.path.isdir(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)
