#!/usr/bin/env python3
"""Merge the English and Chinese HTML reports into one GitHub Pages homepage."""

from __future__ import annotations

import argparse
import re
import shutil
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--en", required=True, type=Path)
    parser.add_argument("--zh", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--assets", type=Path, help="Report assets directory to copy.")
    parser.add_argument(
        "--default-language", choices=("en", "zh"), default="zh"
    )
    return parser.parse_args()


def extract(html: str) -> tuple[str, str]:
    style = re.search(r"<style>(.*?)</style>", html, re.DOTALL)
    body = re.search(r"<body>(.*?)</body>", html, re.DOTALL)
    if not style or not body:
        raise ValueError("report HTML is missing <style> or <body>")
    return style.group(1), body.group(1)


def main() -> None:
    args = parse_args()
    en_style, en_body = extract(args.en.read_text(encoding="utf-8"))
    zh_style, zh_body = extract(args.zh.read_text(encoding="utf-8"))
    if en_style != zh_style:
        # Keep the English stylesheet: both reports share the same renderer.
        pass
    active_en = "active" if args.default_language == "en" else ""
    active_zh = "active" if args.default_language == "zh" else ""

    page = f"""<!doctype html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>video-style-transfer-eval</title>
<style>
{en_style}
.lang {{ display:none; }}
.lang.active {{ display:block; }}
.lang-switch {{ position:fixed; top:18px; right:22px; z-index:40; display:flex; gap:10px; }}
.lang-switch button {{ width:44px; height:44px; border-radius:50%; border:0; background:#102a2f; color:#fff;
  font-size:18px; cursor:pointer; box-shadow:0 6px 18px rgba(24,43,55,.2); line-height:1; }}
.lang-switch button:hover {{ background:#1d5c63; }}
[data-theme="dark"] {{ --ink:#e6eef2; --muted:#9fb0bd; --line:#26353d; --paper:#0c1418; --panel:#141f25; }}
[data-theme="dark"] header {{ background:linear-gradient(125deg,#081519,#0f3337 60%,#164541); }}
[data-theme="dark"] .finding {{ background:#152a2a; }}
[data-theme="dark"] th {{ background:#1b2a31; color:#cfe0e6; }}
[data-theme="dark"] .kpi, [data-theme="dark"] .review-card, [data-theme="dark"] .formula,
[data-theme="dark"] .metric-definition {{ background:#18242b; }}
[data-theme="dark"] .key-table td.best {{ background:#1e4a3c; color:#e6fef3; }}
[data-theme="dark"] .key-table td.second {{ background:#223037; color:#e6eef2; }}
[data-theme="dark"] .availability, [data-theme="dark"] .status.present {{ background:#1e4a3c; color:#bfe9d8; }}
[data-theme="dark"] .status.proxy {{ background:#4a3a1e; color:#f0d6a8; }}
[data-theme="dark"] .status.missing {{ background:#4a2323; color:#f3c1b8; }}
[data-theme="dark"] .kpi-delta.up {{ color:#7fd8bb; }}
[data-theme="dark"] .kpi-delta.down {{ color:#f0a08e; }}
[data-theme="dark"] .bar-track {{ background:#223037; }}
[data-theme="dark"] .table-note, [data-theme="dark"] .small {{ color:#9fb0bd; }}
[data-theme="dark"] .pending {{ color:#9fb0bd; }}
[data-theme="dark"] .metric-card {{ background:#152026; border-color:#26353d; }}
[data-theme="dark"] .metric-card .mm-formula {{ background:#1b2a31; }}
#lang-menu {{ position:absolute; right:0; top:52px; min-width:150px; background:#fff; border:1px solid #dbe2e9;
  border-radius:12px; box-shadow:0 12px 30px rgba(24,43,55,.18); padding:6px; display:none; }}
#lang-menu.open {{ display:block; }}
#lang-menu button {{ display:block; width:100%; text-align:left; border:0; background:transparent; padding:9px 12px;
  border-radius:8px; cursor:pointer; font-size:14px; color:#17212b; }}
#lang-menu button:hover {{ background:#eef6f5; }}
</style>
<script>
window.MathJax = {{ tex: {{ inlineMath: [['$', '$']], displayMath: [['$$', '$$']] }}, svg: {{ fontCache: 'global' }} }};
</script>
<script async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-svg.js"></script>
</head>
<body>
<div class="lang-switch">
  <button id="theme-btn" aria-label="Theme">🌙</button>
  <button id="lang-btn" aria-label="Language">🌐</button>
  <div id="lang-menu">
    <button data-lang="zh">中文</button>
    <button data-lang="en">English</button>
  </div>
</div>
<div id="lang-en" class="lang {active_en}">{en_body}</div>
<div id="lang-zh" class="lang {active_zh}">{zh_body}</div>
<script>
(function () {{
  var menu = document.getElementById('lang-menu');
  var button = document.getElementById('lang-btn');
  function setLang(lang) {{
    document.querySelectorAll('.lang').forEach(function (node) {{
      node.classList.toggle('active', node.id === 'lang-' + lang);
    }});
    document.documentElement.lang = lang;
    menu.classList.remove('open');
    try {{ localStorage.setItem('vst-lang', lang); }} catch (e) {{}}
  }}
  button.addEventListener('click', function (event) {{
    event.stopPropagation();
    menu.classList.toggle('open');
  }});
  menu.querySelectorAll('button').forEach(function (item) {{
    item.addEventListener('click', function () {{ setLang(item.dataset.lang); }});
  }});
  document.addEventListener('click', function () {{ menu.classList.remove('open'); }});
  var themeButton = document.getElementById('theme-btn');
  function setTheme(theme) {{
    document.documentElement.dataset.theme = theme;
    themeButton.textContent = theme === 'dark' ? '☀️' : '🌙';
    try {{ localStorage.setItem('vst-theme', theme); }} catch (e) {{}}
  }}
  themeButton.addEventListener('click', function (event) {{
    event.stopPropagation();
    setTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark');
  }});
  var savedTheme = null;
  try {{ savedTheme = localStorage.getItem('vst-theme'); }} catch (e) {{}}
  setTheme(savedTheme || 'light');
  var saved = null;
  try {{ saved = localStorage.getItem('vst-lang'); }} catch (e) {{}}
  setLang(saved || '{args.default_language}');
}})();
</script>
</body>
</html>
"""
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(page, encoding="utf-8")
    if args.assets and args.assets.is_dir():
        target = args.output.parent / "assets"
        target.mkdir(parents=True, exist_ok=True)
        for item in args.assets.iterdir():
            if item.is_file():
                shutil.copy2(item, target / item.name)
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
