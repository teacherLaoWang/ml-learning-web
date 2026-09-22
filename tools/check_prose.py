"""改文风时的安全网：教案**讲解正文里的数字**必须与原文一致。

用法：
    uv run python tools/check_prose.py                    # 对比 git HEAD 与工作区
    uv run python tools/check_prose.py app/content/lessons/knn.py

只比对「讲解正文」：tagline / story / intuition[] / derivation[].body /
terms[].explain / pitfalls[]。公式区（formula、derivation[].formula、latex、
vars、presets）不在射程内 —— 手写 LaTeX 天然会带进 `\frac{1}{n}` 这种数字，
混进来只会把报警淹掉。公式本身的正确性由 tools/check_tex.mjs + tests/test_tex.py 管。

两条规则：
1. **非公式正文里不许出现原文没有的数字**（挡「顺手编一个数据让类比更可信」）；
   `$...$` 里新增的数字只列出来给人过目 —— LaTeX 记法（`\frac{1}{2}`、`x_{1}`）天然会带数字；
2. **原文任何一个数字都必须还能在新正文里找到**（挡「把带数字的句子整段删掉」，
   也挡「把 0.729 改成 0.999」）。

报警精确到字段：intuition[2] 而不是「这个文件不对」。
"""

from __future__ import annotations

import argparse
import ast
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
NUM = re.compile(r"\d+(?:\.\d+)?")
MATH = re.compile(r"\$[^$\n]*\$")


def numbers(text: str) -> Counter[str]:
    return Counter(NUM.findall(text))


def prose_of(lesson: dict[str, Any]) -> list[tuple[str, str]]:
    """展平成 (字段路径, 文本)，逐段报差异。"""
    out: list[tuple[str, str]] = []
    for key in ("tagline", "story"):
        out.append((key, str(lesson.get(key) or "")))
    for i, p in enumerate(lesson.get("intuition") or []):
        out.append((f"intuition[{i}]", str(p)))
    for i, step in enumerate(lesson.get("derivation") or []):
        out.append((f"derivation[{i}].body", str(step.get("body") or "")))
    for i, t in enumerate(lesson.get("terms") or []):
        out.append((f"terms[{i}].explain", str(t.get("explain") or "")))
    for i, p in enumerate(lesson.get("pitfalls") or []):
        out.append((f"pitfalls[{i}]", str(p)))
    return out


def lesson_from_source(src: str, label: str) -> dict[str, Any] | None:
    """从 .py 源码里把 LESSON 字面量取出来（不 import，避免执行任意代码）。"""
    try:
        tree = ast.parse(src)
    except SyntaxError as exc:
        print(f"  ! {label} 语法不过：{exc}")
        return None
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "LESSON" for t in node.targets
        ):
            try:
                value = ast.literal_eval(node.value)
            except ValueError:  # 教案里混进了非字面量，逐字比对失去意义
                print(f"  ! {label} 的 LESSON 不是纯字面量，跳过")
                return None
            return value if isinstance(value, dict) else None
    print(f"  ! {label} 里没有 LESSON")
    return None


def git_head(key: str) -> str | None:
    r = subprocess.run(
        ["git", "show", f"HEAD:app/content/lessons/{key}.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return r.stdout if r.returncode == 0 else None


def check_key(key: str, work_src: str) -> int:
    head_src = git_head(key)
    if head_src is None:
        print(f"  (HEAD 里没有 {key}.py，跳过)")
        return 0
    old = lesson_from_source(head_src, f"HEAD:{key}")
    new = lesson_from_source(work_src, key)
    if old is None or new is None:
        return 1
    old_prose, new_prose = prose_of(old), prose_of(new)
    notes: list[str] = []
    info: list[str] = []
    if len(old_prose) != len(new_prose):
        notes.append(f"    正文段数变了：{len(old_prose)} → {len(new_prose)}")
    for (path, before), (_again, after) in zip(old_prose, new_prose):
        plain_old, plain_new = numbers(MATH.sub(" ", before)), numbers(MATH.sub(" ", after))
        # 正文（非公式）里凭空多出来的数字 = 编数据，最严重
        invented = plain_new - plain_old - numbers(before)
        if invented:
            notes.append(f"    {path}: 凭空加了数字 {dict(invented)}")
        # 只在 $...$ 里新增的数字 = LaTeX 记法带的，列出来给人过一眼
        only_math = (numbers(after) - numbers(before)) - invented
        if only_math:
            info.append(f"    {path}: 行内公式新增记法 {dict(only_math)}")
    old_all = numbers(" ".join(t for _, t in old_prose))
    new_all = numbers(" ".join(t for _, t in new_prose))
    if old_all - new_all:
        # 原文任何一个数字在新正文里彻底消失 = 把带数字的句子删了或改了
        notes.append(f"    丢了实测数字：{dict(old_all - new_all)}")
    if notes:
        print(f"✗ {key}.py")
        print("\n".join(notes + info))
        return 1
    if info:
        print(f"~ {key}.py  正文数字一致，另有行内公式改写：")
        print("\n".join(info))
        return 0
    print(f"✓ {key}.py  正文数字一致（{sum(old_all.values())} 个）")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="*", type=Path)
    args = ap.parse_args()
    lessons = ROOT / "app/content/lessons"
    if args.paths:
        pairs = [(Path(p).resolve().stem, Path(p).resolve().read_text()) for p in args.paths]
    else:
        pairs = [(p.stem, p.read_text()) for p in sorted(lessons.glob("*.py")) if p.stem != "__init__"]
    bad = sum(check_key(k, src) for k, src in pairs)
    print("——" if bad else "全部通过：讲解正文数字零改动。")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
