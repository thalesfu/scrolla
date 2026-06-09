#!/usr/bin/env python3
"""把 borghese/ 目录下的 Obsidian 笔记转换成 Hugo page bundle。

使用方式：
    python3 scripts/migrate_borghese.py --one "G - 03 Sala III - 阿波罗与达芙妮厅.md" \
        --slug sala-iii-apollo-daphne --title "博尔盖塞美术馆 · 第3室 阿波罗与达芙妮厅"

设计要点：
- 只读 borghese/ 下的源文件，不改动它。
- 每个厅生成 content/posts/borghese/<slug>/index.md，配图复制到同目录。
- 把 ![[any/path/xxx.ext]] 转成 ![](xxx.ext)，统一只取 basename。
- 把非图片 wikilink [[xxx]] 暂时降级为纯文本（试跑阶段，稍后再补站内跳转）。
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
BORGHESE_SRC = ROOT / "borghese"
ATTACH_DIR = BORGHESE_SRC / "attachments"
TARGET_BASE = ROOT / "content" / "posts" / "borghese"

IMG_WIKILINK_RE = re.compile(r"!\[\[([^\]|]+?)(?:\|[^\]]*)?\]\]")
PLAIN_WIKILINK_RE = re.compile(r"(?<!\!)\[\[([^\]|]+?)(?:\|([^\]]+))?\]\]")


def to_basename(target: str) -> str:
    """把 wikilink 里的目标路径压成 basename。"""
    return target.strip().split("/")[-1]


def safe_name(name: str) -> str:
    """Hugo / 浏览器友好：把空格换成下划线，去掉其它会引入歧义的字符。"""
    out = name.replace(" ", "_")
    return out


def demote_headings(text: str) -> str:
    """所有 # 级别整体下移一级，让正文不出现 h1（h1 留给文章页标题）。"""
    def repl(match: re.Match[str]) -> str:
        hashes, rest = match.group(1), match.group(2)
        if len(hashes) >= 6:
            return match.group(0)
        return "#" + hashes + rest
    return re.sub(r"^(#{1,5})( +.*)$", repl, text, flags=re.MULTILINE)


def reorder_intro(body: str) -> str:
    """重排开头：去掉「# 展厅介绍」与「**展厅简介**：」前缀；
    顺序改为：简介正文 → 必看表格 → 图片 → 官网链接，再接「# 核心展品」起的正文。
    若结构不匹配则原样返回。
    """
    # 找到第一个 ## 标题作为结尾边界（# 已被 demote 为 ##）
    m = re.search(r"^## .+$", body, flags=re.MULTILINE)
    if not m:
        return body
    head = body[: m.start()].strip("\n")
    tail = body[m.start():]

    if not head:
        return body

    link_match = re.search(r"^\*\*展厅官网介绍页\*\*[:：][^\n]+", head, flags=re.MULTILINE)
    img_match = re.search(r"^!\[\][^\n]+", head, flags=re.MULTILINE)
    intro_match = re.search(r"^\*\*展厅简介\*\*[:：]\s*(.+)$", head, flags=re.MULTILINE)
    table_match = re.search(
        r"^\*\*必看与核心展品[^\n]*\*\*\s*\n\n(?:\|[^\n]*(?:\n|$))+",
        head,
        flags=re.MULTILINE,
    )

    if not (link_match and img_match and intro_match and table_match):
        return body  # 结构不匹配，保持原样

    intro_para = intro_match.group(1).strip()
    table_block = table_match.group(0).strip()
    img_line = img_match.group(0).strip()
    link_line = link_match.group(0).strip()

    new_head = "\n\n".join([intro_para, table_block, img_line, link_line]) + "\n\n"
    return new_head + tail


def transform_markdown(src_text: str, copied: dict[str, str], missing: list[str]) -> str:
    def img_repl(match: re.Match[str]) -> str:
        target = to_basename(match.group(1))
        src = ATTACH_DIR / target
        if not src.exists():
            missing.append(target)
        new_name = safe_name(target)
        copied[target] = new_name
        return f"![]({new_name})"

    def link_repl(match: re.Match[str]) -> str:
        target, alias = match.group(1), match.group(2)
        return alias.strip() if alias else target.strip()

    text = IMG_WIKILINK_RE.sub(img_repl, src_text)
    text = PLAIN_WIKILINK_RE.sub(link_repl, text)
    text = demote_headings(text)
    return text


def build_frontmatter(title: str, date: str, tags: list[str]) -> str:
    tag_line = ", ".join(f'"{t}"' for t in tags)
    return (
        "---\n"
        f'title: "{title}"\n'
        f"date: {date}\n"
        f"tags: [{tag_line}]\n"
        "draft: false\n"
        "---\n\n"
    )


def migrate_one(src_filename: str, slug: str, title: str, date: str) -> None:
    src = BORGHESE_SRC / src_filename
    if not src.exists():
        sys.exit(f"未找到源文件：{src}")

    target_dir = TARGET_BASE / slug
    target_dir.mkdir(parents=True, exist_ok=True)

    raw = src.read_text(encoding="utf-8")
    if raw.startswith("# "):
        first_line, _, rest = raw.partition("\n")
        body = rest.lstrip("\n")
    else:
        body = raw

    copied: dict[str, str] = {}
    missing: list[str] = []
    body = transform_markdown(body, copied, missing)
    body = reorder_intro(body)

    fm = build_frontmatter(title, date, ["博尔盖塞美术馆", "意大利", "罗马", "艺术"])
    (target_dir / "index.md").write_text(fm + body, encoding="utf-8")

    for orig_name, new_name in sorted(copied.items()):
        src_img = ATTACH_DIR / orig_name
        if not src_img.exists():
            continue
        dst_img = target_dir / new_name
        if dst_img.exists() and dst_img.stat().st_size == src_img.stat().st_size:
            continue
        shutil.copy2(src_img, dst_img)

    print(f"[done] {src_filename} -> {target_dir}")
    print(f"  图片复制：{len(copied)} 张")
    if missing:
        print("  ⚠ 缺失图片：", ", ".join(missing))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--one", required=True, help="borghese 下源 markdown 文件名")
    parser.add_argument("--slug", required=True, help="目标 bundle 目录名")
    parser.add_argument("--title", required=True, help="文章标题")
    parser.add_argument("--date", default="2026-06-30", help="文章日期，默认 2026-06-30")
    args = parser.parse_args()

    migrate_one(args.one, args.slug, args.title, args.date)


if __name__ == "__main__":
    main()
