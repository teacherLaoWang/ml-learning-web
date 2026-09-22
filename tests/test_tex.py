"""Unicode → LaTeX 转录层（app/content/tex.py）的回归测试。

这一层是「公式显示很怪」的根治点，规则都是从真实教案里踩出来的，
改表之前先看这些用例：转录错一个上标，学生学到的就是错的式子。
"""

from __future__ import annotations

import pytest

from app.content import catalog, loader
from app.content.tex import TexError, split_lines, to_latex, to_latex_display


def test_common_notation() -> None:
    assert to_latex("ŷ = w·x + b") == r"\hat{y} = w\cdot x + b"
    assert to_latex("MSE = (1/n)Σ(ŷᵢ − yᵢ)²") == r"MSE = (1/n)\sum (\hat{y}_{i} - y_{i})^{2}"
    assert to_latex("w* = (XᵀX)⁻¹Xᵀy") == r"w* = (X^{T}X)^{-1}X^{T}y"
    assert to_latex("‖w‖₂²") == r"\|w\|_{2}^{2}"
    assert to_latex("∇L = (2/n)·Xᵀ(Xw − y)") == r"\nabla L = (2/n)\cdot X^{T}(Xw - y)"


def test_subscript_wins_over_superscript_for_ijk() -> None:
    """ᵢ ⱼ 在教案里一律是下标（Unicode 没有下标 i，借用了修饰字母）。"""
    assert to_latex("xᵢⱼ") == "x_{ij}"
    assert to_latex("Cᵢₙ") == r"C_{\mathrm{in}}"
    assert to_latex("f⁽¹⁾") == "f^{(1)}"


def test_greek_and_functions_are_upright() -> None:
    assert to_latex("p = σ(z) = 1/(1+e^(−z))") == r"p = \sigma (z) = 1/(1+e^{-z})"
    assert to_latex("μₖ = (1/|Cₖ|)Σ_{{x∈Cₖ}} x") .count(r"\mu _{k}") == 1
    assert r"\ln" in to_latex("ℓ = −[y·ln p + (1−y)·ln(1−p)]")
    assert r"\operatorname*{arg\,min}" in to_latex("argmin_k ‖xᵢ − μₖ‖²")


def test_cjk_gloss_becomes_text() -> None:
    assert to_latex("（收敛）") == r"\text{(收敛)}"
    assert to_latex("P_对") == r"P_{\text{对}}"
    assert to_latex("σ²_噪声") == r"\sigma ^{2}_{\text{噪声}}"
    # 中文下标不能吃掉了后面的英文：`_c　Condorcet` 只应吃掉 c
    assert to_latex("p̄_c　X") == r"\bar{p}_{\mathrm{c}}\text{　}X"


def test_sqrt_takes_a_group() -> None:
    assert to_latex("√(1−βₜ)") == r"\sqrt{1-\beta _{t}}"
    assert to_latex("√ᾱₜ·x₀") == r"\sqrt{\bar{\alpha}_{t}}\cdot x_{0}"


def test_double_superscript_is_merged_not_dropped() -> None:
    """LaTeX 不允许 ⊛^{flip} ^{T}，合并成一个上标而不是报错。"""
    out = to_latex("δₒ ⊛ᶠˡᶦᵖ ᵀ x")
    assert out.count("^{") == 1
    assert r"\star ^{flip\,T}" in out


def test_setminus_and_slash() -> None:
    assert to_latex("Σ_{S ⊆ N\\{j}}") == r"\sum _{S \subseteq N\setminus \{j\}}"


def test_ideographic_space_splits_equations() -> None:
    assert split_lines("a = b　　c = d") == ["a = b", "c = d"]
    # 单个全角空格是「A → B」这种连着写的分隔，不能断成两行
    assert split_lines("L₁ = … 　→　 w* = …") == ["L₁ = … 　→　 w* = …"]
    assert len(to_latex_display("a=b　　c=d").split(r"\\")) == 2
    assert to_latex_display("a=b") == "a=b"


def test_unknown_character_raises_instead_of_guessing() -> None:
    with pytest.raises(TexError) as exc:
        to_latex("x ☃ y")
    assert "☃" in str(exc.value)


def test_empty_formula_raises() -> None:
    with pytest.raises(TexError):
        to_latex("   ")


# ------------------------------------------------------- 全站覆盖率（防回退） ----


def test_every_formula_in_the_catalog_has_latex() -> None:
    """任何一条公式都必须能给出 latex；转不动就是缺字符，必须补表或手写。"""
    missing: list[str] = []
    keys = [item["key"] for fam in catalog.FAMILIES for item in fam["items"]]
    for key in keys:
        payload = loader.payload(key)
        formula = payload["formula"]
        if formula.get("text") and not formula.get("latex"):
            missing.append(f"{key}.formula")
        for i, step in enumerate(payload["derivation"]):
            if step.get("formula") and not step.get("latex"):
                missing.append(f"{key}.derivation[{i}]")
        for i, var in enumerate(formula.get("vars") or []):
            if var.get("sym") and not var.get("latex"):
                missing.append(f"{key}.vars[{i}]")
    assert not missing, f"这些公式没转出 latex（补 app/content/tex.py 的字符表）：{missing}"


def test_latex_keeps_every_number_of_the_source() -> None:
    """转录不能把教案里的数字弄丢 —— 数字是实测值，比排版重要。"""
    import re
    from collections import Counter

    nums = re.compile(r"\d+(?:\.\d+)?")
    gaps: list[str] = []
    for key in [item["key"] for fam in catalog.FAMILIES for item in fam["items"]]:
        payload = loader.payload(key)
        pairs = [(payload["formula"].get("text", ""), payload["formula"].get("latex", ""))]
        pairs += [(s.get("formula", ""), s.get("latex", "")) for s in payload["derivation"]]
        for src, tex in pairs:
            if not src or not tex:
                continue
            lost = Counter(nums.findall(src)) - Counter(nums.findall(tex))
            if lost:
                gaps.append(f"{key}: 丢了 {dict(lost)} ← {src[:40]}")
    assert not gaps, "公式转录吃掉数字了：\n" + "\n".join(gaps)
