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
html, body { margin: 0 !important; padding: 0 !important; background: #eef2f6 !important; }
main { max-width: none !important; padding: 0 !important; background: transparent !important; }
main > section {
  width: 1228px !important;
  height: 668px !important;
  margin: 26px auto !important;
  padding: 44px 54px 58px !important;
  box-sizing: border-box !important;
  overflow: hidden !important;
  page-break-after: always !important;
  break-after: page !important;
  background: #ffffff !important;
  border-radius: 20px !important;
  border: 1px solid #e3e9f1 !important;
  box-shadow: 0 14px 34px rgba(16, 36, 56, 0.07) !important;
  display: flex !important;
  flex-direction: column !important;
  justify-content: flex-start !important;
}
main > header {
  width: 1280px !important;
  height: 720px !important;
  margin: 0 !important;
  padding: 96px 84px !important;
  box-sizing: border-box !important;
  overflow: hidden !important;
  page-break-after: always !important;
  break-after: page !important;
  border-radius: 0 !important;
  background: linear-gradient(135deg, #123e4a 0%, #1d5c63 60%, #24707a 100%) !important;
  color: #fff !important;
  display: flex !important;
  flex-direction: column !important;
  justify-content: center !important;
}
main > header h1 { font-size: 52px !important; line-height: 1.16 !important; color: #fff !important; margin: 0 0 22px !important; letter-spacing: 0.01em; }
main > header p { font-size: 18px !important; line-height: 1.7 !important; color: #dbe9ec !important; margin: 0 0 6px !important; }
main > header strong { color: #ffffff !important; }
main > header code, main > header a { color: #ffffff !important; }
main > section:last-child { page-break-after: auto !important; break-after: auto !important; }
main > section h2 { font-size: 34px !important; margin: 0 0 18px !important; color: #123e4a !important; letter-spacing: 0.01em; }
main > section h3 { font-size: 31px !important; margin: 0 0 16px !important; color: #123e4a !important; letter-spacing: 0.01em; }
main > section table { font-size: 17px !important; }
main > section th { padding: 11px 12px !important; }
main > section td { padding: 10px 12px !important; }
main > section p, main > section li { font-size: 16.5px !important; line-height: 1.62 !important; }
main > section ul { padding-left: 22px !important; }
.page-inner { transform-origin: top left; }
.slide-footer {
  position: absolute; left: 54px; right: 54px; bottom: 18px;
  display: flex; justify-content: space-between;
  font-size: 12px; color: #8394a8; letter-spacing: 0.02em;
}
.case-slide .case-group h3 { font-size: 18px !important; font-weight: 500 !important; color: #6b7f94 !important; margin: 0 0 8px !important; }
.case-slide .case-group table { font-size: 12px !important; }
.case-slide .case-group th, .case-slide .case-group td { padding: 3px 5px !important; }
.case-slide .case-group img { width: 100% !important; height: auto !important; border-radius: 10px !important; margin: 12px auto 0 !important; display: block !important; }
"""

SLIDE_JS = r"""
(function () {
  function run() {
  // flatten nested result tables so each table becomes its own page
  [...document.querySelectorAll('main > section')].forEach((parent) => {
    const children = [...parent.children].filter((node) => node.tagName === 'SECTION');
    if (children.length) {
      children.slice().reverse().forEach((child) => parent.after(child));
      parent.remove();
    }
  });

  // the appendix stays in the report; case pages come from the manifest
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
  }

  const images = [...document.images];
  Promise.all(images.map((img) => {
    if (img.complete) return Promise.resolve();
    return new Promise((resolve) => { img.onload = resolve; img.onerror = resolve; });
  })).then(run);
})();
"""



def inject_cases(html_text: str, case_manifest: Path, lang: str) -> str:
    import json
    import re

    entries = json.loads(case_manifest.read_text(encoding="utf-8"))
    slides = [entry for entry in entries if entry.get("total", 1) > 1]
    if not slides:
        slides = entries
    zh = lang == "zh"
    blocks = []
    for index, entry in enumerate(slides, start=1):
        heading = (
            f"案例研究（{index} / {len(slides)}）"
            if zh
            else f"Case studies ({index} / {len(slides)})"
        )
        blocks.append(
            "<section class='case-slide'>"
            f"<h3>{heading}</h3>"
            f"<img src='assets/{entry['image']}' alt='case study'>"
            "</section>"
        )
    match = re.search(r"<section><h2>(?:结论|Conclusion)", html_text)
    if not match:
        return html_text
    return html_text[: match.start()] + "".join(blocks) + html_text[match.start():]


def build(report_html: Path, out_dir: Path, lang: str, case_manifest: Path | None = None) -> Path:
    html_text = report_html.read_text(encoding="utf-8")
    if case_manifest and case_manifest.is_file():
        html_text = inject_cases(html_text, case_manifest, lang)
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
    parser.add_argument("--case-manifest", type=Path)
    args = parser.parse_args()
    build(args.report_html, args.out_dir, args.language, args.case_manifest)


if __name__ == "__main__":
    main()
