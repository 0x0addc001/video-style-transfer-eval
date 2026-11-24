#!/usr/bin/env python3
"""Regenerate the README screenshots from the current HTML reports."""

from __future__ import annotations

import argparse
from pathlib import Path

from playwright.sync_api import sync_playwright


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--en", required=True, type=Path)
    parser.add_argument("--zh", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    return parser.parse_args()


SHOTS = {
    "en": {
        "html": None,
        "tables": "Quantitative results",
        "metrics": "A. Metric definitions",
    },
    "zh": {
        "html": None,
        "tables": "定量结果",
        "metrics": "A. 指标定义",
    },
}


def capture(page, selector: str | None, path: Path) -> None:
    if selector:
        page.get_by_text(selector, exact=False).first.scroll_into_view_if_needed()
        page.wait_for_timeout(250)
    page.screenshot(path=str(path))
    print(f"Wrote {path}")


def main() -> None:
    args = parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        for lang, report in (("en", args.en), ("zh", args.zh)):
            page.goto(report.resolve().as_uri())
            page.wait_for_timeout(400)
            for name, selector in SHOTS[lang].items():
                if selector is None:
                    page.evaluate("window.scrollTo(0, 0)")
                capture(page, selector, args.out_dir / f"report-{lang}-{name}.png")
        browser.close()


if __name__ == "__main__":
    main()
