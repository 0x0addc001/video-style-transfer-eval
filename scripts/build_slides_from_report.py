#!/usr/bin/env python3
"""Turn a report HTML into a paginated slide deck using the report's own modules."""

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

PAGE_CSS = """
@page { size: 13.333in 7.5in; margin: 0; }
html, body { margin: 0 !important; padding: 0 !important; background: #fff !important; }
main { max-width: none !important; padding: 0 !important; }
main > header, main > section {
  width: 1280px !important;
  height: 720px !important;
  margin: 0 !important;
  padding: 46px 56px !important;
  box-sizing: border-box !important;
  overflow: hidden !important;
  page-break-after: always !important;
  break-after: page !important;
  border-radius: 0 !important;
  box-shadow: none !important;
}
main > header { background: linear-gradient(135deg,#123e4a,#1d5c63) !important; color: #fff !important; }
main > header h1, main > header strong, main > header code, main > header a { color: #fff !important; }
main > section:last-child { page-break-after: auto !important; break-after: auto !important; }
.page-inner { transform-origin: top left; }
"""

SLIDE_JS = r"""
(function () {
  // flatten nested result tables so each table becomes its own page
  [...document.querySelectorAll('main > section')].forEach((parent) => {
    const children = [...parent.children].filter((node) => node.tagName === 'SECTION');
    if (children.length) {
      children.slice().reverse().forEach((child) => parent.after(child));
      parent.remove();
    }
  });

  // the appendix is evidence, not presentation: keep it in the report only
  const appendix = document.querySelector('main > section.appendix');
  if (appendix) appendix.remove();

  const pages = [...document.querySelectorAll('main > header, main > section')];
  pages.forEach((page) => {
    const inner = document.createElement('div');
    inner.className = 'page-inner';
    while (page.firstChild) inner.appendChild(page.firstChild);
    page.appendChild(inner);
    const style = getComputedStyle(page);
    const availW = page.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight);
    const availH = page.clientHeight - parseFloat(style.paddingTop) - parseFloat(style.paddingBottom);
    inner.style.width = availW + 'px';
    let height = inner.scrollHeight;
    let width = inner.scrollWidth;
    let scale = Math.min(1, availH / Math.max(height, 1), availW / Math.max(width, 1));
    inner.style.width = (availW / scale) + 'px';
    height = inner.scrollHeight;
    width = inner.scrollWidth;
    scale = Math.min(scale, availH / Math.max(height, 1), availW / Math.max(width, 1));
    inner.style.width = (availW / scale) + 'px';
    inner.style.transform = 'scale(' + scale + ')';
  });
})();
"""


def build(report_html: Path, out_dir: Path, lang: str) -> Path:
    html_text = report_html.read_text(encoding="utf-8")
    html_text = html_text.replace("</head>", f"<style>{PAGE_CSS}</style></head>", 1)
    html_text = html_text.replace("</body>", f"<script>{SLIDE_JS}</script></body>", 1)

    out_dir.mkdir(parents=True, exist_ok=True)
    source_assets = report_html.parent / "assets"
    if source_assets.is_dir():
        target_assets = out_dir / "assets"
        if not target_assets.is_dir():
            import shutil

            shutil.copytree(source_assets, target_assets)
    slide_html = out_dir / f"slides_{lang}.html"
    slide_html.write_text(html_text, encoding="utf-8")

    pdf_path = out_dir / f"slides_{lang}.pdf"
    subprocess.run(
        [
            CHROME,
            "--headless=new",
            "--no-pdf-header-footer",
            "--virtual-time-budget=15000",
            f"--print-to-pdf={pdf_path}",
            slide_html.resolve().as_uri(),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    print("wrote", slide_html, "and", pdf_path if pdf_path.is_file() else "(pdf failed)")
    return slide_html


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-html", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--language", choices=["zh", "en"], required=True)
    args = parser.parse_args()
    build(args.report_html, args.out_dir, args.language)


if __name__ == "__main__":
    main()
