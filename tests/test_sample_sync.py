"""The published homepage must come from the same run as the sample report."""

from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "examples" / "sample_report" / "evaluation_report"
REPORT = max(REPORT_DIR.glob("report_zh_VST-*.html"), key=lambda p: p.stat().st_mtime)
HOMEPAGE = ROOT / "docs" / "index.html"
REPORT_ID = re.compile(r"VST-\d{8}T\d{6}-[0-9a-f]{12}")


class SampleSyncTest(unittest.TestCase):
    def test_homepage_and_report_share_a_report_id(self) -> None:
        report = REPORT.read_text(encoding="utf-8")
        homepage = HOMEPAGE.read_text(encoding="utf-8")
        report_ids = set(REPORT_ID.findall(report))
        homepage_ids = set(REPORT_ID.findall(homepage))
        self.assertTrue(report_ids, "sample report has no report ID")
        self.assertEqual(report_ids, homepage_ids)
        self.assertIn('id="lang-en"', homepage)
        self.assertIn('id="lang-zh"', homepage)


if __name__ == "__main__":
    unittest.main()
