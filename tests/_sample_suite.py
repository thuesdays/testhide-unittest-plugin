"""
Sample tests exercised by test_conformance.py. Intentionally NOT named test_*.py so
neither unittest discovery nor pytest collects these (some are designed to fail) — they
are run explicitly by the conformance test and asserted on via the emitted report.
"""
import unittest

import testhide_unittest as th


class SampleTests(unittest.TestCase):
    def test_pass(self):
        "A passing sample."
        th.set_info('{"env": "staging"}')
        th.attach("https://example.com/ok.png")
        self.assertTrue(True)

    def test_fail(self):
        "A failing sample."
        th.attach("/tmp/shot.png")
        self.assertEqual(1, 2)

    def test_error(self):
        "An erroring sample."
        raise RuntimeError("boom")

    @unittest.skip("not ready")
    def test_skip(self):
        self.fail("should not run")

    @unittest.expectedFailure
    def test_xfail(self):
        "Known-issue sample."
        self.assertEqual(1, 2)
