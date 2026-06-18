#!/usr/bin/env python3
"""把 BasilicaDiSanPietro/ 目录下的 Obsidian 笔记转换成 Hugo page bundle。

参考 scripts/migrate_borghese.py 的设计，但针对梵蒂冈博物馆 + 西斯廷 + 圣彼得三段
内容做了调整：

- 不做 borghese 那种 reorder_intro（这套源文件开头不是 `**展厅简介**：…` 的标准格式，
  reorder 反而会破结构），只做 wikilink → markdown、图片复制、标题降级、首行 H1 处理。
- 目标目录：content/posts/vatican/<slug>/。
- 封面 cover 路径占位为 /images/posts/covers/vatican-<slug>-painting.jpg，
  实际图片由后续单独生成；frontmatter 里的占位让 PaperMod 暂不报错的话由模板兜底——
  当前先按"占位路径"写入 frontmatter，后续补图替换。
- 视频附件（.mp4 等）也跟着复制过去；wikilink 转成 markdown 的图片语法对视频不合适，
  这里不特殊处理（数量极少，仅 1 个），让最终页面手动调整或留作降级链接。

用法：
    # 单篇（slug/title 必填）
    python3 scripts/migrate_vatican.py --one "V - 01 入口与松果院 + 八角庭院（拉奥孔 + 观景楼阿波罗）.md" \
        --slug pinecone-octagonal --title "梵蒂冈博物馆 · 入口与松果院 + 八角庭院"

    # 全量
    python3 scripts/migrate_vatican.py --all
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT / "BasilicaDiSanPietro"
ATTACH_DIR = SRC_DIR / "attachments"
TARGET_BASE = ROOT / "content" / "posts" / "vatican"

IMG_WIKILINK_RE = re.compile(r"!\[\[([^\]|]+?)(?:\|[^\]]*)?\]\]")
PLAIN_WIKILINK_RE = re.compile(r"(?<!\!)\[\[([^\]|]+?)(?:\|([^\]]+))?\]\]")

# (源文件名, slug, 标题, 是否剥离首行 H1)
# 顺序按官方参观动线：V → R → S → B；总览 / 拍照机位 / 全图集放最前。
MANIFEST: list[tuple[str, str, str, bool]] = [
    ("00 总览.md", "overview",
     "梵蒂冈博物馆 + 西斯廷礼拜堂 + 圣彼得大教堂 · 总览", True),
    ("00 拍照机位.md", "photo-spots",
     "梵蒂冈博物馆 + 圣彼得大教堂 · 拍照机位", True),
    ("V - 01 入口与松果院 + 八角庭院（拉奥孔 + 观景楼阿波罗）.md", "v01-pinecone-octagonal",
     "梵蒂冈博物馆 · 入口与松果院 + 八角庭院（拉奥孔 + 观景楼阿波罗）", True),
    ("V - 02 缪斯厅 + 圆形厅 + 希腊十字厅（古典雕塑精选）.md", "v02-muses-rotunda-greek-cross",
     "梵蒂冈博物馆 · 缪斯厅 + 圆形厅 + 希腊十字厅（古典雕塑精选）", True),
    ("V - 03 地图廊 + 挂毯廊 + 烛台廊（穿行段挑看）.md", "v03-three-galleries",
     "梵蒂冈博物馆 · 地图廊 + 挂毯廊 + 烛台廊（穿行段挑看）", True),
    ("V - 03A 地图廊全图集（40 幅地图）.md", "v03a-gallery-of-maps",
     "梵蒂冈博物馆 · 地图廊全图集（40 幅地图）", True),
    ("V - 03B 挂毯廊全图集（基督生平 + 乌尔班八世）.md", "v03b-gallery-of-tapestries",
     "梵蒂冈博物馆 · 挂毯廊全图集（基督生平 + 乌尔班八世）", True),
    ("V - 04 支线 · 埃及馆 + 伊特鲁里亚馆 + 梵蒂冈花园（调研备查，未必去）.md", "v04-egypt-etruscan-gardens",
     "梵蒂冈博物馆 · 支线 · 埃及馆 + 伊特鲁里亚馆 + 梵蒂冈花园", True),
    ("R - 05 拉斐尔房间 · 君士坦丁厅.md", "r05-stanza-di-costantino",
     "拉斐尔房间 · 君士坦丁厅", True),
    ("R - 06 拉斐尔房间 · 赫利奥多罗斯厅.md", "r06-stanza-di-eliodoro",
     "拉斐尔房间 · 赫利奥多罗斯厅", True),
    ("R - 07 拉斐尔房间 · 签字厅《雅典学院》《圣礼之争》.md", "r07-stanza-della-segnatura",
     "拉斐尔房间 · 签字厅《雅典学院》《圣礼之争》", True),
    ("R - 08 拉斐尔房间 · 波尔戈火灾厅.md", "r08-stanza-incendio-borgo",
     "拉斐尔房间 · 波尔戈火灾厅", True),
    # S-08 首行 H1 是 `# 这座礼拜堂是什么`，是正文小节，不剥。
    ("S - 08 西斯廷礼拜堂 · 天顶《创世纪》九场景 + 先知女巫.md", "s08-sistine-ceiling",
     "西斯廷礼拜堂 · 天顶《创世纪》九场景 + 先知女巫", False),
    ("S - 09 西斯廷礼拜堂 · 祭坛墙《最后的审判》.md", "s09-sistine-last-judgment",
     "西斯廷礼拜堂 · 祭坛墙《最后的审判》", True),
    ("S - 10 西斯廷礼拜堂 · 两侧墙 + 入口墙壁画带.md", "s10-sistine-side-walls",
     "西斯廷礼拜堂 · 两侧墙 + 入口墙壁画带", True),
    ("B - 10 圣彼得大教堂 · 建筑史 + 外立面 + 广场柱廊.md", "b10-architecture-square",
     "圣彼得大教堂 · 建筑史 + 外立面 + 广场柱廊", True),
    ("B - 11 圣彼得大教堂 · 内部必看（圣殇 + 华盖 + 宝座 + 穹顶内部）.md", "b11-interior",
     "圣彼得大教堂 · 内部必看（圣殇 + 华盖 + 宝座 + 穹顶内部）", True),
    ("B - 12 圣彼得大教堂 · 登顶穹顶攻略（台阶 + 票价 + 排队 + 值不值）.md", "b12-dome-climb",
     "圣彼得大教堂 · 登顶穹顶攻略", True),
]


def to_basename(target: str) -> str:
    return target.strip().split("/")[-1]


def safe_name(name: str) -> str:
    return name.replace(" ", "_")


def demote_headings(text: str) -> str:
    def repl(match: re.Match[str]) -> str:
        hashes, rest = match.group(1), match.group(2)
        if len(hashes) >= 6:
            return match.group(0)
        return "#" + hashes + rest
    return re.sub(r"^(#{1,5})( +.*)$", repl, text, flags=re.MULTILINE)


def build_filename_to_slug() -> dict[str, str]:
    out: dict[str, str] = {}
    for filename, slug, _title, _strip in MANIFEST:
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


def build_frontmatter(title: str, date: str, slug: str, tags: list[str]) -> str:
    tag_line = ", ".join(f'"{t}"' for t in tags)
    cover_path = f"/images/posts/covers/vatican-{slug}-painting.jpg"
    return (
        "---\n"
        f'title: "{title}"\n'
        f"date: {date}\n"
        f"tags: [{tag_line}]\n"
        "draft: false\n"
        f'cover: {{image: "{cover_path}", alt: "{title}"}}\n'
        "---\n\n"
    )


def migrate_one(src_filename: str, slug: str, title: str, date: str, strip_h1: bool) -> None:
    src = SRC_DIR / src_filename
    if not src.exists():
        sys.exit(f"未找到源文件：{src}")
    target_dir = TARGET_BASE / slug
    target_dir.mkdir(parents=True, exist_ok=True)

    raw = src.read_text(encoding="utf-8")
    if strip_h1 and raw.startswith("# "):
        _first_line, _, rest = raw.partition("\n")
        body = rest.lstrip("\n")
    else:
        body = raw

    copied: dict[str, str] = {}
    missing: list[str] = []
    body = transform_markdown(body, copied, missing)

    fm = build_frontmatter(
        title,
        date,
        slug,
        ["梵蒂冈博物馆", "西斯廷礼拜堂", "圣彼得大教堂", "意大利", "罗马", "艺术"],
    )
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
    g.add_argument("--one", help="BasilicaDiSanPietro 下源 markdown 文件名（单篇模式）")
    g.add_argument("--all", action="store_true", help="按内置 manifest 处理全部条目")
    parser.add_argument("--slug", help="单篇模式下的 bundle 目录名")
    parser.add_argument("--title", help="单篇模式下的文章标题")
    parser.add_argument("--date", default="2026-06-18", help="文章日期，默认 2026-06-18")
    args = parser.parse_args()

    if args.all:
        # 越靠前的条目给越晚的时间戳（PaperMod 列表按日期倒序）。
        base = datetime.fromisoformat(f"{args.date}T00:00:00")
        total = len(MANIFEST)
        for idx, (filename, slug, title, strip_h1) in enumerate(MANIFEST):
            offset_hours = total - 1 - idx
            stamp = base + timedelta(hours=offset_hours - total)
            dated = stamp.strftime("%Y-%m-%dT%H:%M:%S+08:00")
            migrate_one(filename, slug, title, dated, strip_h1)
        return

    if not (args.slug and args.title):
        parser.error("--one 模式需要同时提供 --slug 与 --title")
    # 单篇模式：默认走"剥首行 H1"
    migrate_one(args.one, args.slug, args.title, args.date, True)


if __name__ == "__main__":
    main()
