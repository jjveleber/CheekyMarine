#!/usr/bin/env python3
"""Self-test of check_notices.py: mutated copies of THIRD_PARTY_NOTICES must fail.

Usage: test_check_notices.py THIRD_PARTY_NOTICES
"""
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CHECK = os.path.join(HERE, "check_notices.py")
NOTICES = sys.argv.pop(1) if len(sys.argv) > 1 else os.path.join(HERE, "..", "..", "THIRD_PARTY_NOTICES")
ISC_ROW = "  supercluster.hpp, vector-tile, geojson.hpp, geometry.hpp   ISC"


def run(text):
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "NOTICES")
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        r = subprocess.run([sys.executable, "-I", CHECK, path], capture_output=True, text=True)
        return r.returncode, r.stdout + r.stderr


class CheckNotices(unittest.TestCase):
    def setUp(self):
        with open(NOTICES, encoding="utf-8") as f:
            self.text = f.read()
        self.assertIn(ISC_ROW + "\n", self.text)
        self.assertIn("\nISC license text\n", self.text)

    def test_committed_file_passes(self):
        code, out = run(self.text)
        self.assertEqual(code, 0, out)

    def test_missing_text_fails(self):
        code, out = run(self.text.replace("\nISC license text\n", "\nISC text\n"))
        self.assertEqual(code, 1, out)
        self.assertIn("ISC", out)

    def test_two_space_row_without_its_text_fails(self):
        mutated = self.text.replace(ISC_ROW, ISC_ROW.replace("   ISC", "  ISC"))
        mutated = mutated.replace("\nISC license text\n", "\nISC text\n")
        code, out = run(mutated)
        self.assertEqual(code, 1, out)
        self.assertIn("ISC", out)

    def test_row_with_no_license_column_fails(self):
        code, out = run(self.text.replace(ISC_ROW, ISC_ROW.replace("   ISC", " ISC")))
        self.assertEqual(code, 1, out)


if __name__ == "__main__":
    unittest.main()
