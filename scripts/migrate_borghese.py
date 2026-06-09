#!/usr/bin/env python3
"""把 borghese/ 目录下的 Obsidian 笔记转换成 Hugo page bundle。

使用方式：
    # 单篇
    python3 scripts/migrate_borghese.py --one "G - 03 Sala III - 阿波罗与达芙妮厅.md" \
        --slug sala-iii-apollo-daphne --title "博尔盖塞美术馆 · 第 3 室 阿波罗与达芙妮厅"

    # 批量（按内置 manifest 处理所有 21 个厅 + 总览）
    python3 scripts/migrate_borghese.py --all

设计要点：
- 只读 borghese/ 下的源文件，不改动它。
- 每个厅生成 content/posts/borghese/<slug>/index.md，配图复制到同目录。
- 把 ![[any/path/xxx.ext]] 转成 ![](xxx.ext)，统一只取 basename，文件名空格换下划线。
- 把非图片 wikilink 优先按 manifest 解析为站内相对链接（../<slug>/）；
  匹配不到的降级为纯文本，保留可读性。
- 标题整体降级一级（# → ##），让正文不出现 h1。
- 开头重排为：简介句子 → 必看表格 → 图片 → 官网链接。
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BORGHESE_SRC = ROOT / "borghese"
ATTACH_DIR = BORGHESE_SRC / "attachments"
TARGET_BASE = ROOT / "content" / "posts" / "borghese"

IMG_WIKILINK_RE = re.compile(r"!\[\[([^\]|]+?)(?:\|[^\]]*)?\]\]")
PLAIN_WIKILINK_RE = re.compile(r"(?<!\!)\[\[([^\]|]+?)(?:\|([^\]]+))?\]\]")

# (源文件名, slug, 标题) — slug 与人类可读路径同步演进
MANIFEST: list[tuple[str, str, str]] = [
    ("00 总览.md", "overview", "博尔盖塞美术馆 · 总览与必看 TOP 10"),
    ("G - 00 Entrance Hall  - 入口大厅.md", "entrance-hall", "博尔盖塞美术馆 · 入口大厅"),
    ("G - 01 Sala I - 保利娜厅.md", "sala-i-paolina", "博尔盖塞美术馆 · 第 1 室 保利娜厅"),
    ("G - 02 Sala II - 大卫厅.md", "sala-ii-david", "博尔盖塞美术馆 · 第 2 室 大卫厅"),
    ("G - 03 Sala III - 阿波罗与达芙妮厅.md", "sala-iii-apollo-daphne", "博尔盖塞美术馆 · 第 3 室 阿波罗与达芙妮厅"),
    ("G - 04 Sala IV - 凯撒厅.md", "sala-iv-emperors", "博尔盖塞美术馆 · 第 4 室 凯撒厅"),
    ("G - 05 Sala V - 双性人厅.md", "sala-v-hermaphrodite", "博尔盖塞美术馆 · 第 5 室 双性人厅"),
    ("G - 06 Sala VI - 埃涅阿斯厅.md", "sala-vi-aeneas", "博尔盖塞美术馆 · 第 6 室 埃涅阿斯厅"),
    ("G - 07 Sala VII - 埃及厅.md", "sala-vii-egyptian", "博尔盖塞美术馆 · 第 7 室 埃及厅"),
    ("G - 08 Sala VIII - 卡拉瓦乔厅.md", "sala-viii-caravaggio", "博尔盖塞美术馆 · 第 8 室 卡拉瓦乔厅"),
    ("L1 - 09 Sala IX - 狄多厅.md", "sala-ix-dido", "博尔盖塞美术馆 · 第 9 室 狄多厅"),
    ("L1 - 10 Sala X - 赫拉克勒斯厅.md", "sala-x-hercules", "博尔盖塞美术馆 · 第 10 室 赫拉克勒斯厅"),
    ("L1 - 11 Sala XI - 费拉拉绘画厅.md", "sala-xi-ferrara", "博尔盖塞美术馆 · 第 11 室 费拉拉绘画厅"),
    ("L1 - 12 Sala XII - 巴克坎特厅.md", "sala-xii-bacchae", "博尔盖塞美术馆 · 第 12 室 巴克坎特厅"),
    ("L1 - 13 Sala XIII - 声望厅.md", "sala-xiii-fame", "博尔盖塞美术馆 · 第 13 室 声望厅"),
    ("L1 - 14 Sala XIV - 兰弗兰科凉廊.md", "sala-xiv-lanfranco", "博尔盖塞美术馆 · 第 14 室 兰弗兰科凉廊"),
    ("L1 - 15 Sala XV - 黎明女神厅.md", "sala-xv-aurora", "博尔盖塞美术馆 · 第 15 室 黎明女神厅"),
    ("L1 - 16 Sala XVI - 花神厅.md", "sala-xvi-flora", "博尔盖塞美术馆 · 第 16 室 花神厅"),
    ("L1 - 17 Sala XVII - 昂热伯爵厅.md", "sala-xvii-angerville", "博尔盖塞美术馆 · 第 17 室 昂热伯爵厅"),
    ("L1 - 18 Sala XVIII - 朱庇特与安提俄佩厅.md", "sala-xviii-jupiter-antiope", "博尔盖塞美术馆 · 第 18 室 朱庇特与安提俄佩厅"),
    ("L1 - 19 Sala XIX - 海伦与帕里斯厅.md", "sala-xix-helen-paris", "博尔盖塞美术馆 · 第 19 室 海伦与帕里斯厅"),
    ("L1 - 20 Sala XX - 普绪刻厅.md", "sala-xx-psyche", "博尔盖塞美术馆 · 第 20 室 普绪刻厅"),
]


def to_basename(target: str) -> str:
    """把 wikilink 里的目标路径压成 basename。"""
    return target.strip().split("/")[-1]


def safe_name(name: str) -> str:
    """Hugo / 浏览器友好：把空格换成下划线。"""
    return name.replace(" ", "_")


def demote_headings(text: str) -> str:
    """所有 # 级别整体下移一级，让正文不出现 h1（h1 留给文章页标题）。"""
    def repl(match: re.Match[str]) -> str:
        hashes, rest = match.group(1), match.group(2)
        if len(hashes) >= 6:
            return match.group(0)
        return "#" + hashes + rest
    return re.sub(r"^(#{1,5})( +.*)$", repl, text, flags=re.MULTILINE)


def reorder_intro(body: str) -> str:
    """重排开头：去掉「**展厅简介**：」前缀；
    顺序改为：简介正文 → 必看表格 → 图片 → 官网链接，再接「## 核心展品」起的正文。
    若结构不匹配则原样返回。
    """
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
        return body

    intro_para = intro_match.group(1).strip()
    table_block = table_match.group(0).strip()
    img_line = img_match.group(0).strip()
    link_line = link_match.group(0).strip()

    new_head = "\n\n".join([intro_para, table_block, img_line, link_line]) + "\n\n"
    return new_head + tail


def build_filename_to_slug() -> dict[str, str]:
    """从 manifest 反推：源文件 basename（去掉 .md）→ slug。
    用于把 wikilink 里出现的源文件名解析成站内 slug。
    """
    out: dict[str, str] = {}
    for filename, slug, _ in MANIFEST:
        stem = filename[:-3] if filename.endswith(".md") else filename
        out[stem] = slug
    return out


FILENAME_TO_SLUG = build_filename_to_slug()


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
        stem = to_basename(target).strip()
        label = (alias or stem).strip()
        slug = FILENAME_TO_SLUG.get(stem)
        if slug:
            return f"[{label}](../{slug}/)"
        return label

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
        _first_line, _, rest = raw.partition("\n")
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

    print(f"[done] {src_filename} -> {target_dir.relative_to(ROOT)}")
    print(f"  图片复制：{len(copied)} 张")
    if missing:
        print("  ⚠ 缺失图片：", ", ".join(sorted(set(missing))))


def main() -> None:
    parser = argparse.ArgumentParser()
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--one", help="borghese 下源 markdown 文件名（单篇模式）")
    g.add_argument("--all", action="store_true", help="按内置 manifest 处理全部条目")
    parser.add_argument("--slug", help="单篇模式下的 bundle 目录名")
    parser.add_argument("--title", help="单篇模式下的文章标题")
    parser.add_argument("--date", default="2026-06-09", help="文章日期，默认 2026-06-09")
    args = parser.parse_args()

    if args.all:
        for filename, slug, title in MANIFEST:
            migrate_one(filename, slug, title, args.date)
        return

    if not (args.slug and args.title):
        parser.error("--one 模式需要同时提供 --slug 与 --title")
    migrate_one(args.one, args.slug, args.title, args.date)


if __name__ == "__main__":
    main()
