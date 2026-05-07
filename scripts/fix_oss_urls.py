#!/usr/bin/env python3
"""Fix remaining oss.thalesfu.com URLs in href and data attributes of generated markdown files."""
import re
from pathlib import Path

POSTS_DIR = Path("/Users/thalesfu/codes/github.com/thalesfu/scrolla/content/posts")

def oss_url_to_local(url):
    url = url.split("?")[0]
    match = re.match(r'https?://oss\.thalesfu\.com/(.+)', url)
    if match:
        return "/images/posts/" + match.group(1)
    return None

def fix_file(path):
    text = path.read_text(encoding="utf-8")
    original = text

    def replace_oss_attr(m):
        url = m.group(1)
        local = oss_url_to_local(url)
        if local:
            return m.group(0).replace(url, local)
        return m.group(0)

    # Replace all OSS URLs in any attribute value (href, data-full-url, etc.)
    text = re.sub(
        r'https?://oss\.thalesfu\.com/[^"\')\s]+',
        lambda m: oss_url_to_local(m.group(0)) or m.group(0),
        text
    )

    if text != original:
        path.write_text(text, encoding="utf-8")
        print(f"Fixed: {path.name}")

for f in POSTS_DIR.glob("*.md"):
    fix_file(f)

print("Done.")
