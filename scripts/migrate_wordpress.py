#!/usr/bin/env python3
"""
Migrate WordPress posts from MySQL to Hugo markdown files.
- Converts Gutenberg HTML to Markdown via pandoc
- Downloads OSS images to static/images/posts/
- Downloads external images that are still accessible
- Preserves original publication dates and tags
"""

import os
import re
import subprocess
import urllib.request
import urllib.error
from pathlib import Path
import mysql.connector

# Config
MYSQL_USER = "root"
MYSQL_PASS = "Thales@429"
MYSQL_DB = "thalesfuwordpress"
PROJECT_ROOT = Path("/Users/thalesfu/codes/github.com/thalesfu/scrolla")
POSTS_DIR = PROJECT_ROOT / "content/posts"
IMAGES_DIR = PROJECT_ROOT / "static/images/posts"
OSS_BUCKET = "oss://thalesfu"
OSS_BASE_URL = "http://oss.thalesfu.com"


def get_db():
    return mysql.connector.connect(
        host="127.0.0.1",
        user=MYSQL_USER,
        password=MYSQL_PASS,
        database=MYSQL_DB,
        charset="utf8mb4"
    )


def html_to_markdown(html):
    html = re.sub(r'<!-- /?wp:[^>]* -->', '', html)
    html = html.strip()
    if not html:
        return ""
    result = subprocess.run(
        ["pandoc", "-f", "html", "-t", "markdown_strict", "--wrap=none"],
        input=html, capture_output=True, text=True
    )
    md = result.stdout
    md = re.sub(r'\n{3,}', '\n\n', md)
    return md.strip()


def oss_path_from_url(url):
    url = url.split("?")[0]
    match = re.match(r'https?://oss\.thalesfu\.com/(.+)', url)
    if match:
        return match.group(1)
    return None


def download_oss_image(obj_path, local_abs):
    if local_abs.exists():
        return True
    local_abs.parent.mkdir(parents=True, exist_ok=True)
    oss_uri = f"{OSS_BUCKET}/{obj_path}"
    result = subprocess.run(
        ["aliyun", "oss", "cp", oss_uri, str(local_abs)],
        capture_output=True, text=True
    )
    return result.returncode == 0


def download_external_image(url, post_id):
    url_clean = url.split("?")[0]
    filename = re.sub(r'[^\w.-]', '_', Path(url_clean).name)
    if not filename or filename == ".":
        filename = "image.jpg"
    local_abs = IMAGES_DIR / "external" / str(post_id) / filename
    md_ref = f"/images/posts/external/{post_id}/{filename}"

    if local_abs.exists():
        return md_ref

    local_abs.parent.mkdir(parents=True, exist_ok=True)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = resp.read()
        local_abs.write_bytes(data)
        print(f"    [external] Downloaded: {url}")
        return md_ref
    except Exception as e:
        print(f"    [external] Failed ({e.__class__.__name__}): {url}")
        return None


def replace_images_in_markdown(content, post_id):
    oss_pattern = re.compile(
        r'(!\[[^\]]*\]\()(https?://oss\.thalesfu\.com[^\)]+)(\))'
    )
    external_pattern = re.compile(
        r'(!\[[^\]]*\]\()(https?://(?!oss\.thalesfu\.com)[^\)]+)(\))'
    )
    html_img_oss = re.compile(
        r'(<img[^>]+src=")(https?://oss\.thalesfu\.com[^"]+)("[^>]*>)'
    )
    html_img_ext = re.compile(
        r'(<img[^>]+src=")(https?://(?!oss\.thalesfu\.com)[^"]+)("[^>]*>)'
    )

    def replace_oss(m):
        url = m.group(2).strip()
        obj_path = oss_path_from_url(url)
        if not obj_path:
            return m.group(0)
        local_abs = IMAGES_DIR / obj_path
        md_ref = "/images/posts/" + obj_path
        ok = download_oss_image(obj_path, local_abs)
        if ok:
            print(f"    [oss] OK: {obj_path}")
            return m.group(1) + md_ref + m.group(3)
        print(f"    [oss] FAIL: {obj_path}")
        return m.group(0)

    def replace_external(m):
        url = m.group(2).strip()
        ref = download_external_image(url, post_id)
        if ref:
            return m.group(1) + ref + m.group(3)
        return m.group(0)

    def replace_html_oss(m):
        url = m.group(2).strip()
        obj_path = oss_path_from_url(url)
        if not obj_path:
            return m.group(0)
        local_abs = IMAGES_DIR / obj_path
        md_ref = "/images/posts/" + obj_path
        ok = download_oss_image(obj_path, local_abs)
        if ok:
            return m.group(1) + md_ref + m.group(3)
        return m.group(0)

    def replace_html_ext(m):
        url = m.group(2).strip()
        ref = download_external_image(url, post_id)
        if ref:
            return m.group(1) + ref + m.group(3)
        return m.group(0)

    content = oss_pattern.sub(replace_oss, content)
    content = external_pattern.sub(replace_external, content)
    content = html_img_oss.sub(replace_html_oss, content)
    content = html_img_ext.sub(replace_html_ext, content)
    return content


def slug_from_title(title):
    slug = re.sub(r'[^\w一-鿿]', '-', title)
    slug = re.sub(r'-+', '-', slug).strip('-')
    return slug.lower()


def tag_yaml_line(tags):
    if not tags:
        return ""
    clean = list(dict.fromkeys([t.strip() for t in tags.split("|") if t.strip()]))
    if not clean:
        return ""
    items = ", ".join(f'"{t}"' for t in clean)
    return f"\ntags: [{items}]"


def main():
    POSTS_DIR.mkdir(parents=True, exist_ok=True)
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)

    db = get_db()
    cursor = db.cursor(dictionary=True)

    cursor.execute("""
        SELECT p.ID, p.post_title, p.post_date, p.post_content,
        (
            SELECT GROUP_CONCAT(t2.name ORDER BY t2.name SEPARATOR '|')
            FROM wp_term_relationships tr2
            JOIN wp_term_taxonomy tt2 ON tr2.term_taxonomy_id = tt2.term_taxonomy_id
            JOIN wp_terms t2 ON tt2.term_id = t2.term_id
            WHERE tr2.object_id = p.ID AND tt2.taxonomy IN ('category','post_tag')
        ) as tags
        FROM wp_posts p
        WHERE p.post_type='post' AND p.post_status='publish'
        ORDER BY p.post_date ASC
    """)
    posts = cursor.fetchall()
    cursor.close()
    db.close()

    print(f"Found {len(posts)} posts to migrate.\n")

    for post in posts:
        pid = post["ID"]
        title = post["post_title"]
        date = str(post["post_date"])[:10]
        tags = post.get("tags") or ""
        html = post["post_content"] or ""

        print(f"[{pid}] {title} ({date})")

        md_content = html_to_markdown(html)
        md_content = replace_images_in_markdown(md_content, pid)

        fm = f'---\ntitle: "{title}"\ndate: {date}'
        fm += tag_yaml_line(tags)
        fm += "\ndraft: false\n---\n\n"

        slug = slug_from_title(title)
        filename = f"{date}-{slug}.md"
        filepath = POSTS_DIR / filename
        filepath.write_text(fm + md_content, encoding="utf-8")
        print(f"  -> {filename}\n")

    print("Migration complete.")


if __name__ == "__main__":
    main()
