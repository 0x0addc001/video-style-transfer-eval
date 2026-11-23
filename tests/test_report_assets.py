"""Contact-sheet path handling survives Windows- and POSIX-authored metrics."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from render_report import asset_name, resolve_asset_source  # noqa: E402


class ContactSheetPathTest(unittest.TestCase):
    def test_windows_path_basename(self) -> None:
        value = r"D:\_Engineering\Project\demo_evaluation\contact_sheets\demo_case_01.jpg"
        self.assertEqual(asset_name(value), "demo_case_01.jpg")

    def test_posix_path_basename(self) -> None:
        self.assertEqual(
            asset_name("/tmp/run/contact_sheets/demo_case_01.jpg"),
            "demo_case_01.jpg",
        )

    def test_relative_path_resolves_against_metrics_dir(self) -> None:
        resolved = resolve_asset_source(
            "contact_sheets/demo_case_01.jpg", Path("/tmp/run")
        )
        self.assertEqual(
            resolved, Path("/tmp/run/contact_sheets/demo_case_01.jpg")
        )

    def test_windows_relative_path_is_normalized(self) -> None:
        resolved = resolve_asset_source(
            r"contact_sheets\demo_case_01.jpg", Path("/tmp/run")
        )
        self.assertEqual(
            resolved, Path("/tmp/run/contact_sheets/demo_case_01.jpg")
        )

    def test_absolute_path_is_preserved(self) -> None:
        resolved = resolve_asset_source(
            "/srv/eval/contact_sheets/demo_case_01.jpg", Path("/tmp/run")
        )
        self.assertEqual(
            resolved, Path("/srv/eval/contact_sheets/demo_case_01.jpg")
        )


if __name__ == "__main__":
    unittest.main()
