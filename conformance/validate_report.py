#!/usr/bin/env python3
"""
Testhide Report Format v1 — conformance validator (stdlib only).

Usage:
    python validate_report.py <report.xml> [--strict]

Exit codes:
    0  no errors (warnings allowed, unless --strict)
    1  one or more errors (or warnings when --strict)
    2  bad usage / file not found / unparseable XML

This is the executable form of docs/specs/REPORT-FORMAT-V1.md. Every official Testhide
reporting plugin vendors a copy of this file + golden_report.xml and runs, in CI:

    python validate_report.py <generated_report.xml>

against a sample run, to guarantee the agent will parse it correctly.

No third-party dependencies — runs anywhere Python 3.8+ is available (incl. .NET / Node / Go
CI runners that just need a Python step).
"""
import sys
import xml.etree.ElementTree as ET

SCHEMA_VERSION = "1"

RESOLUTIONS = {
    "Passed", "Skipped", "Collection Error", "Teardown Error",
    "Known Issue", "Need to reopen", "Resolved in branch",
    "Verified at Branch", "Unresolved",
}


def _local(tag):
    """Strip XML namespace: '{ns}testcase' -> 'testcase'."""
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else tag


def _child(el, name):
    for c in el:
        if _local(c.tag) == name:
            return c
    return None


def _children(el, name):
    return [c for c in el if _local(c.tag) == name]


def _iter(root, name):
    for el in root.iter():
        if _local(el.tag) == name:
            yield el


class Report:
    def __init__(self):
        self.errors = []
        self.warnings = []

    def err(self, msg):
        self.errors.append(msg)

    def warn(self, msg):
        self.warnings.append(msg)


def _suite_properties(suite):
    props = {}
    pc = _child(suite, "properties")
    if pc is not None:
        for p in _children(pc, "property"):
            n = p.get("name")
            if n:
                props[n] = p.get("value", "")
    return props


def _validate_testcase(tc, r, idx):
    where = f"testcase[{idx}]"
    name = tc.get("name")
    if not name:
        r.err(f"{where}: missing required attribute 'name'")
    else:
        where = f"testcase '{name}'"

    if tc.get("classname") is None:
        r.err(f"{where}: missing required attribute 'classname'")

    time_v = tc.get("time")
    if time_v is None:
        r.err(f"{where}: missing required attribute 'time'")
    else:
        try:
            float(time_v)
        except ValueError:
            r.err(f"{where}: attribute 'time'='{time_v}' is not a float")

    if tc.get("file") is None or tc.get("line") is None:
        r.warn(f"{where}: missing 'file'/'line' (recommended for code-impact matching)")

    failure = _child(tc, "failure")
    error = _child(tc, "error")
    skipped = _child(tc, "skipped")
    is_failing = failure is not None or error is not None

    # Exactly one (or zero) outcome child
    outcomes = sum(x is not None for x in (failure, error, skipped))
    if outcomes > 1:
        r.err(f"{where}: has multiple outcome children (failure/error/skipped) — emit at most one")

    for el, kind in ((failure, "failure"), (error, "error")):
        if el is not None and not (el.get("message") or "").strip():
            r.err(f"{where}: <{kind}> missing non-empty 'message' attribute")

    # fail_id rules: failing tests REQUIRE a non-empty fail_id; non-failing tests
    # should leave it empty/absent (parser defaults absent -> "").
    fail_id = (tc.get("fail_id") or "").strip()
    if is_failing:
        if not fail_id:
            r.err(f"{where}: failing test must have a non-empty 'fail_id'")
    elif fail_id:
        r.warn(f"{where}: non-failing test has a non-empty 'fail_id' (should be empty)")

    # test_resolution
    res = tc.get("test_resolution")
    if res is None:
        r.warn(f"{where}: missing 'test_resolution' (parser defaults to 'Unresolved')")
    elif res not in RESOLUTIONS:
        r.warn(f"{where}: test_resolution='{res}' not in the v1 closed set")

    # per-test properties
    pc = _child(tc, "properties")
    if pc is not None:
        for p in _children(pc, "property"):
            pname = p.get("name")
            pval = p.get("value")
            if not pname:
                r.err(f"{where}: <property> missing 'name'")
                continue
            if pname == "attachment" and not (pval or "").strip():
                r.err(f"{where}: attachment property has empty 'value'")

    return failure, error, skipped


def validate(path, strict=False):
    r = Report()
    try:
        tree = ET.parse(path)
    except ET.ParseError as e:
        print(f"ERROR: not well-formed XML: {e}", file=sys.stderr)
        return 2
    root = tree.getroot()

    if _local(root.tag) not in ("testsuites", "testsuite"):
        r.err(f"root element is <{_local(root.tag)}>; expected <testsuites> or <testsuite> "
              f"(only the JUnit dialect carries Testhide rich fields)")

    suites = list(_iter(root, "testsuite"))
    if not suites:
        r.err("no <testsuite> found")

    total_tc = 0
    for suite in suites:
        props = _suite_properties(suite)
        ver = props.get("testhide_schema_version")
        if ver is None:
            r.warn("<testsuite> missing 'testhide_schema_version' property (agent assumes 1)")
        elif ver != SCHEMA_VERSION:
            r.warn(f"testhide_schema_version='{ver}' (this validator targets v{SCHEMA_VERSION})")
        if not suite.get("timestamp"):
            r.warn("<testsuite> missing 'timestamp' (agent synthesizes per-test start from it)")

        tcs = _children(suite, "testcase")
        fails = errs = skips = 0
        for i, tc in enumerate(tcs):
            total_tc += 1
            failure, error, skipped = _validate_testcase(tc, r, i)
            fails += failure is not None
            errs += error is not None
            skips += skipped is not None

        # count cross-check (warning only — backend recomputes)
        for attr, actual in (("tests", len(tcs)), ("failures", fails),
                             ("errors", errs), ("skipped", skips)):
            decl = suite.get(attr)
            if decl is not None:
                try:
                    if int(decl) != actual:
                        r.warn(f"<testsuite> {attr}='{decl}' but counted {actual}")
                except ValueError:
                    r.warn(f"<testsuite> {attr}='{decl}' is not an integer")

    if total_tc == 0:
        r.warn("report contains zero <testcase> elements")

    # --- report ---
    for w in r.warnings:
        print(f"WARN:  {w}")
    for e in r.errors:
        print(f"ERROR: {e}", file=sys.stderr)

    n_e, n_w = len(r.errors), len(r.warnings)
    print(f"\n{path}: {n_e} error(s), {n_w} warning(s).")
    if n_e:
        return 1
    if strict and n_w:
        print("(--strict: warnings treated as failure)")
        return 1
    print("OK - conforms to Testhide Report Format v1.")
    return 0


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("-")]
    strict = "--strict" in argv[1:]
    if len(args) != 1:
        print(__doc__)
        return 2
    return validate(args[0], strict=strict)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
