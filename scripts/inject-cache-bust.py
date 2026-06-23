#!/usr/bin/env python3
"""Inject deploy version query strings into docs HTML before GitHub Pages upload."""

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

VERSION = sys.argv[1] if len(sys.argv) > 1 else "dev"
DOCS = Path(__file__).resolve().parent.parent / "docs"

PATTERNS = [
    (re.compile(r'(href="(?:\.\./)?css/styles\.css)(?:\?[^"]*)?"'), rf'\1?v={VERSION}"'),
    (re.compile(r'(src="(?:\.\./)?js/app\.js)(?:\?[^"]*)?"'), rf'\1?v={VERSION}"'),
    (re.compile(r'(href="(?:\.\./)?favicon-32\.png)(?:\?[^"]*)?"'), rf'\1?v={VERSION}"'),
    (re.compile(r'(href="(?:\.\./)?favicon-16\.png)(?:\?[^"]*)?"'), rf'\1?v={VERSION}"'),
]

for html in DOCS.rglob("*.html"):
    text = html.read_text(encoding="utf-8")
    for pattern, repl in PATTERNS:
        text = pattern.sub(repl, text)
    html.write_text(text, encoding="utf-8")
    print(f"cache-bust: {html.relative_to(DOCS.parent)}")

build_info = {
    "version": VERSION,
    "builtAt": datetime.now(timezone.utc).isoformat(),
}
(DOCS / "build-info.json").write_text(json.dumps(build_info, indent=2) + "\n", encoding="utf-8")
print(f"wrote build-info.json ({VERSION})")
