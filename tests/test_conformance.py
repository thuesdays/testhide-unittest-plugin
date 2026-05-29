"""
End-to-end: run the sample suite under TesthideTestRunner and assert the emitted report
(a) validates against the vendored conformance kit and (b) carries the right fields.
"""
import importlib.util
import os
import tempfile
import unittest
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_validator = _load(os.path.join(REPO, "conformance", "validate_report.py"), "thv_validate")
_sample = _load(os.path.join(HERE, "_sample_suite.py"), "thv_sample")

from testhide_unittest import TesthideTestRunner  # noqa: E402


class ConformanceTest(unittest.TestCase):
    def _run_sample(self):
        out = os.path.join(tempfile.mkdtemp(), "report.xml")
        suite = unittest.TestLoader().loadTestsFromModule(_sample)
        with open(os.devnull, "w") as devnull:
            TesthideTestRunner(report_path=out, verbosity=0, stream=devnull).run(suite)
        return out

    def test_report_validates(self):
        out = self._run_sample()
        self.assertTrue(os.path.isfile(out), "report file was not written")
        self.assertEqual(_validator.validate(out), 0, "report did not conform to v1")

    def test_report_fields(self):
        out = self._run_sample()
        suite = ET.parse(out).getroot().find("testsuite")
        self.assertIsNotNone(suite)

        # schema version present and == 1
        versions = [p.get("value") for p in suite.iter("property")
                    if p.get("name") == "testhide_schema_version"]
        self.assertEqual(versions, ["1"])

        # counts: 5 tests, fail+xfail -> 2 failures, 1 error, 1 skipped
        self.assertEqual(suite.get("tests"), "5")
        self.assertEqual(suite.get("failures"), "2")
        self.assertEqual(suite.get("errors"), "1")
        self.assertEqual(suite.get("skipped"), "1")

        cases = {tc.get("name"): tc for tc in suite.findall("testcase")}

        self.assertEqual(cases["test_pass"].get("test_resolution"), "Passed")
        self.assertEqual(cases["test_pass"].get("fail_id"), "")
        pass_props = {p.get("name"): p.get("value") for p in cases["test_pass"].iter("property")}
        self.assertIn("attachment", pass_props)
        self.assertIn("info", pass_props)
        self.assertIn("docstr", pass_props)

        self.assertTrue(cases["test_fail"].get("fail_id"), "failing test must have fail_id")
        self.assertIsNotNone(cases["test_fail"].find("failure"))

        self.assertIsNotNone(cases["test_error"].find("error"))
        self.assertTrue(cases["test_error"].get("fail_id"))

        self.assertIsNotNone(cases["test_skip"].find("skipped"))
        self.assertEqual(cases["test_skip"].get("test_resolution"), "Skipped")

        self.assertEqual(cases["test_xfail"].get("test_resolution"), "Known Issue")
        self.assertIsNotNone(cases["test_xfail"].find("failure"))


if __name__ == "__main__":
    unittest.main()
