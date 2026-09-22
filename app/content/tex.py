"""把教案里用 Unicode 拼写的公式转成 LaTeX，交给前端 KaTeX 渲染。

教案原文保持可读的 Unicode（ŷᵢ²ᵀΣ…），这样后端、命令行、离线 JSON 里都能直接读。
前端显示时不能原样塞给 KaTeX，所以这里做一层**保守**的转录：

- 认识表里的字符才翻译，不认识的非 ASCII 字符一律抛 :class:`TexError`；
- 调用方（loader）捕获异常后回退成原文本 —— 页面顶多沿用旧的等宽显示，
  绝不会把公式悄悄转错。教学站里错一个上标就是错一个概念。

所以新增教案时如果转录失败，``tests/test_tex.py`` 会直接指出缺的是哪个字符：
要么补表，要么在该条教案里手写 ``"latex"`` 字段（歧义公式一律手写，例如 Σ 到底是
求和号还是协方差矩阵，程序判断不了）。
"""

from __future__ import annotations

import re

__all__ = ["TexError", "split_lines", "to_latex", "to_latex_display"]


class TexError(ValueError):
    """遇到不认识的非 ASCII 字符 —— 宁可不渲染，也不能猜。"""


# ------------------------------------------------------- 上标 / 下标字符表 ----
# 注意：U+1D62 ᵢ、U+2C7C ⱼ、U+1DA3-1DA5 ᵣᵤᵥ 在教学文本里都是**下标**写法
# （没有真正的下标 i，所以借用了这一批），而 U+2071 ⁱ、ʳ 才是上标。
SUBSCRIPTS = {
    "₀": "0", "₁": "1", "₂": "2", "₃": "3", "₄": "4",
    "₅": "5", "₆": "6", "₇": "7", "₈": "8", "₉": "9",
    "₍": "(", "₎": ")", "₊": "+", "₋": "-",
    "ₐ": "a", "ₔ": "e", "ₑ": "e", "ₕ": "h", "ₖ": "k", "ₗ": "l",
    "ₘ": "m", "ₙ": "n", "ₚ": "p", "ₛ": "s", "ₜ": "t", "ₓ": "x", "ₒ": "o",
    "ᵢ": "i", "ⱼ": "j", "ᵣ": "r", "ᵤ": "u", "ᵥ": "v",
    "ᵦ": "beta", "ᵧ": "gamma", "ᵨ": "rho", "ᵩ": "phi", "ᵪ": "chi",
}

SUPERSCRIPTS = {
    "⁰": "0", "¹": "1", "²": "2", "³": "3", "⁴": "4",
    "⁵": "5", "⁶": "6", "⁷": "7", "⁸": "8", "⁹": "9",
    "⁽": "(", "⁾": ")", "⁺": "+", "⁻": "-",
    "ⁿ": "n", "ⁱ": "i", "ʳ": "r", "ˢ": "s", "ᵗ": "t",
    "ᵖ": "p", "ᵏ": "k", "ᵃ": "a", "ᵇ": "b", "ᶜ": "c", "ᵈ": "d",
    "ᵉ": "e", "ᶠ": "f", "ᵍ": "g", "ʰ": "h", "ʲ": "j", "ˡ": "l",
    "ᵐ": "m", "ᵒ": "o", "ᵠ": "phi", "ᵡ": "chi",
    "ˣ": "x", "ʸ": "y", "ᶻ": "z", "ᶲ": "phi", "ᶱ": "theta",
    "ᶦ": "i", "ᶫ": "L", "ᶰ": "N", "ᶸ": "U",
    "ᵀ": "T", "ᴬ": "A", "ᴮ": "B", "ᴰ": "D", "ᴱ": "E", "ᴳ": "G",
    "ᴴ": "H", "ᴵ": "I", "ᴶ": "J", "ᴷ": "K", "ᴸ": "L", "ᴹ": "M",
    "ᴺ": "N", "ᴼ": "O", "ᴾ": "P", "ᴿ": "R", "ᵁ": "U", "ⱽ": "V", "ᵂ": "W",
    "ᵞ": "gamma",
}

# 组合附加符（基字符 + U+0302 尖号 / U+0304 横线 / U+0303 波浪）
COMBINING = {"̂": r"\hat{%s}", "̄": r"\bar{%s}", "̃": r"\tilde{%s}", "̆": r"\breve{%s}"}

# 预组合好的「字母 + 附加符」单码点（ŷ 在 Unicode 里是一个码点，不是序列）
PRECOMPOSED = {
    "ŷ": r"\hat{y}", "ȳ": r"\bar{y}", "ẑ": r"\hat{z}", "x̂": r"\hat{x}",
    "ᾱ": r"\bar{\alpha}",
    "ê": r"\hat{e}", "î": r"\hat{\imath}", "ñ": r"\tilde{n}",
    "â": r"\hat{a}", "Ä": r"\ddot{A}", "ÿ": r"\ddot{y}",
    "Â": r"\hat{A}", "Ŝ": r"\hat{S}", "ŝ": r"\hat{s}", "ẏ": r"\dot{y}",
    "ā": r"\bar{a}", "ē": r"\bar{e}", "ī": r"\bar{\imath}", "ō": r"\bar{o}",
    "ô": r"\hat{o}", "p̄": r"\bar{p}", "t̄": r"\bar{t}", "m̄": r"\bar{m}",
    "d̄": r"\bar{d}", "x̄": r"\bar{x}", "z̄": r"\bar{z}", "y̆": r"\breve{y}",
}

# 希腊字母。KaTeX 的大小写命令不对称（\Sigma / \sigma），所以逐个显式映射。
GREEK = {
    "α": r"\alpha", "β": r"\beta", "γ": r"\gamma", "δ": r"\delta",
    "ε": r"\varepsilon", "ζ": r"\zeta", "η": r"\eta", "θ": r"\theta",
    "ι": r"\iota", "κ": r"\kappa", "λ": r"\lambda", "μ": r"\mu",
    "ν": r"\nu", "ξ": r"\xi", "ο": r"o", "π": r"\pi", "ρ": r"\rho",
    "σ": r"\sigma", "ς": r"\varsigma", "τ": r"\tau", "υ": r"\upsilon",
    "φ": r"\varphi", "ϕ": r"\phi", "χ": r"\chi", "ψ": r"\psi", "ω": r"\omega",
    "Γ": r"\Gamma", "Δ": r"\Delta", "Θ": r"\Theta", "Λ": r"\Lambda",
    "Ξ": r"\Xi", "Π": r"\Pi", "Ρ": r"P", "Υ": r"\Upsilon", "Φ": r"\Phi",
    "Ψ": r"\Psi", "Ω": r"\Omega",
    "ϵ": r"\epsilon", "ϑ": r"\vartheta", "ϖ": r"\varpi",
    "ϰ": r"\varkappa", "ϱ": r"\varrho",
}

# 运算符 / 关系符 / 定界符 / 中文标点
SYMBOLS = {
    "−": "-", "–": "-", "‐": "-", "—": r"\text{---}", "―": r"\text{---}",
    "×": r"\times", "÷": r"\div", "±": r"\pm", "∓": r"\mp",
    "·": r"\cdot", "⋅": r"\cdot", "∙": r"\cdot",
    "≤": r"\le", "≥": r"\ge", "≠": r"\ne", "≈": r"\approx",
    "≡": r"\equiv", "∼": r"\sim", "∽": r"\sim", "≁": r"\nsim",
    "∝": r"\propto", "∣": r"\mid",
    "→": r"\to", "←": r"\leftarrow", "↔": r"\leftrightarrow",
    "↦": r"\mapsto", "⇒": r"\Rightarrow", "⇐": r"\Leftarrow",
    "⇔": r"\Leftrightarrow", "⟹": r"\Longrightarrow", "⟸": r"\Longleftarrow",
    "∂": r"\partial", "∇": r"\nabla", "∫": r"\int", "∮": r"\oint",
    "∑": r"\sum", "∏": r"\prod", "∐": r"\coprod",
    "Σ": r"\sum",  # 少数表示协方差矩阵的（歧义）条目标了 latex 手写，见教案
    "√": r"\sqrt", "∛": r"\sqrt[3]", "∜": r"\sqrt[4]",
    "∞": r"\infty",
    "∈": r"\in", "∉": r"\notin", "∪": r"\cup", "∩": r"\cap",
    "⊆": r"\subseteq", "⊂": r"\subset", "⊇": r"\supseteq", "⊃": r"\supset",
    "∀": r"\forall", "∃": r"\exists", "∧": r"\land", "∨": r"\lor",
    "¬": r"\neg", "⊕": r"\oplus", "⊗": r"\otimes", "⊘": r"\oslash",
    "⊙": r"\odot", "⊛": r"\star", "⊖": r"\ominus", "⊞": r"\boxplus",
    "‖": r"\|", "∥": r"\parallel", "⟂": r"\perp",
    "⌈": r"\lceil", "⌉": r"\rceil", "⌊": r"\lfloor", "⌋": r"\rfloor",
    "〈": r"\langle", "〉": r"\rangle", "⟨": r"\langle", "⟩": r"\rangle",
    "′": "'", "″": "''", "…": r"\ldots", "⋯": r"\cdots",
    "°": r"^{\circ}", "ℓ": r"\ell", "ℝ": r"\mathbb{R}", "ℕ": r"\mathbb{N}",
    "ℤ": r"\mathbb{Z}", "𝔽": r"\mathbb{F}",
    "½": r"\frac{1}{2}", "⅓": r"\frac{1}{3}", "⅔": r"\frac{2}{3}",
    "¼": r"\frac{1}{4}", "¾": r"\frac{3}{4}",
    "＋": "+", "－": "-", "＝": "=", "＜": "<", "＞": ">",
    "（": "(", "）": ")", "［": "[", "］": "]", "｛": r"\{", "｝": r"\}",
    "，": "，", "、": "、", "。": "。", "：": "：", "；": "；",
    # 教案里的 { } 都是集合括号，直接进 LaTeX 会变成不可见的分组
    "{": r"\{", "}": r"\}",
}

# 教案里用「上标字母 + 下标字母」混排出来的下标词（Unicode 没有对应的下标 n）。
# 值里含反斜杠，不能再进主循环走一遍，所以先换成 \x00N\x01 占位、最后再还原。
SEQUENCES = {
    "Cᵢₙ": r"C_{\mathrm{in}}",
    "Cₒᵤₜ": r"C_{\mathrm{out}}",
    "ₒᵤₜ": r"_{\mathrm{out}}",
}

# 函数名：直接写字母会被排成斜体变量，得换成 \ln 这类正名字令
FUNCTIONS = {
    "softmax": r"\operatorname{softmax}", "sigmoid": r"\operatorname{sigmoid}",
    "argmax": r"\operatorname*{arg\,max}", "argmin": r"\operatorname*{arg\,min}",
    "log": r"\log", "ln": r"\ln", "exp": r"\exp", "max": r"\max",
    "min": r"\min", "det": r"\det", "tr": r"\operatorname{tr}",
    "trace": r"\operatorname{tr}", "sign": r"\operatorname{sign}",
    "sgn": r"\operatorname{sgn}", "diag": r"\operatorname{diag}",
    "rank": r"\operatorname{rank}", "var": r"\operatorname{Var}",
    "cov": r"\operatorname{Cov}", "mod": r"\bmod", "atan": r"\arctan",
    "tanh": r"\tanh", "ReLU": r"\operatorname{ReLU}", "avg": r"\operatorname{avg}",
    "median": r"\operatorname{median}", "std": r"\operatorname{std}",
    "majority": r"\operatorname{majority}",
}
# 下划线也算标识符字符，\b 在 "argmin_k" 里不成立，所以自己界定边界。
_FUNC_RE = re.compile(
    r"(?<![A-Za-z])(" + "|".join(re.escape(f) for f in sorted(FUNCTIONS, key=len, reverse=True)) + r")(?![A-Za-z])"
)
_CJK_RE = re.compile(r"[\u3000-\u303f\u4e00-\u9fff\uff00-\uffef]")
_ASCII_SAFE = set("+-*/=<>(),.|[]^_!?'\"&#%:;@~ $0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ")


def split_lines(text: str) -> list[str]:
    """教案用全角空格把几条公式挤在一行，这里拆开分别排版。"""
    parts = re.split(r"\u3000{2,}|[，;]\s*\u3000|\s{3,}", text.strip())
    return [p.strip() for p in parts if p.strip()]


def _match_paren(text: str, start: int) -> int:
    """text[start] 是 '('，返回配对 ')' 的下标；不配对返回 -1。"""
    depth = 0
    for k in range(start, len(text)):
        if text[k] == "(":
            depth += 1
        elif text[k] == ")":
            depth -= 1
            if depth == 0:
                return k
    return -1


def _match_brace(text: str, start: int) -> int:
    """text[start] 是 '{'，返回配对 '}' 的下标；不配对返回 -1。"""
    depth = 0
    for k in range(start, len(text)):
        if text[k] == "{":
            depth += 1
        elif text[k] == "}":
            depth -= 1
            if depth == 0:
                return k
    return -1


_CJK_STOP = set("　、。，．：；（）「」【】！？")


def _cjk_word(ch: str) -> bool:
    """算「词」的中文（下标里的「噪声」），标点空白不算，免得吃掉后面的英文。"""
    return bool(_CJK_RE.match(ch)) and ch not in _CJK_STOP


def _plain(ch: str) -> str:
    """上/下标字符 → 普通 ASCII。"""
    return SUBSCRIPTS.get(ch) or SUPERSCRIPTS.get(ch) or ""


def to_latex(text: str) -> str:
    """单行 Unicode 公式 → LaTeX。表里没有的非 ASCII 字符抛 :class:`TexError`。"""
    if not text or not text.strip():
        raise TexError("空公式")

    raw: list[str] = []
    for src, dst in SEQUENCES.items():
        if src in text:
            raw.append(dst)
            text = text.replace(src, f"\x00{len(raw) - 1}\x01")

    out: list[str] = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]

        if ch == "\x00":  # 已经是成品 LaTeX 片段，原样放行
            end = text.index("\x01", i)
            out.append(raw[int(text[i + 1 : end])])
            i = end + 1
            continue
        if ch == "√":
            if i + 1 < n and text[i + 1] == "(":
                end = _match_paren(text, i + 1)
                if end > 0:  # \sqrt 必须吃一个群，\sqrt(...) 会被 KaTeX 判错
                    out.append("\\sqrt{" + to_latex(text[i + 2 : end]) + "}")
                    i = end + 1
                    continue
            j = i + 1  # 裸根号（√ᾱₜ）：把后面「原子 + 上下标」整串收进根号
            while j < n and (
                text[j].isalnum()
                or text[j] in GREEK
                or text[j] in PRECOMPOSED
                or text[j] in SUBSCRIPTS
                or text[j] in SUPERSCRIPTS
            ):
                j += 1
            if j > i + 1:
                out.append("\\sqrt{" + to_latex(text[i + 1 : j]) + "}")
                i = j
                continue
        if ch in PRECOMPOSED:
            out.append(PRECOMPOSED[ch])
            i += 1
            continue
        if ch.isascii() and ch.isalpha() and i + 1 < n and text[i + 1] in COMBINING:
            out.append(COMBINING[text[i + 1]] % ch)
            i += 2
            continue
        if ch in COMBINING:
            prev = out.pop() if out else ""
            out.append(COMBINING[ch] % prev)
            i += 1
            continue

        # 成串的上标 / 下标 → 一个 ^{...} 或 _{...}
        for table, mark in ((SUPERSCRIPTS, "^"), (SUBSCRIPTS, "_")):
            if ch in table:
                j, body = i, []
                while j < n and (text[j] in table or text[j] in PRECOMPOSED):
                    if text[j] in table:
                        body.append(_plain(text[j]) if table is SUPERSCRIPTS else SUBSCRIPTS[text[j]])
                    else:
                        body.append(PRECOMPOSED[text[j]])
                    j += 1
                inner = "".join(body).replace("{", "").replace("}", "")
                out.append(f"{mark}{{{inner}}}")
                i = j
                break
        else:
            if _CJK_RE.match(ch):
                j, buf = i, []
                while j < n and _CJK_RE.match(text[j]):
                    buf.append(SYMBOLS.get(text[j], text[j]))
                    j += 1
                out.append(r"\text{" + "".join(buf) + "}")
                i = j
                continue
            if ch in "_^" and i + 1 < n and text[i + 1] == "(":
                end = _match_paren(text, i + 1)
                if end > 0:  # e^(−z) 写成 ^(…) 会多一圈括号，直接收成 ^{-z}
                    out.append(ch + "{" + to_latex(text[i + 2 : end]) + "}")
                    i = end + 1
                    continue
            if ch in "_^" and i + 1 < n and text[i + 1] == "{":
                end = _match_brace(text, i + 1)
                if end > 0:  # Σ_{x∈Cₖ}：教案里已经写好的花括号下标
                    out.append(ch + "{" + to_latex(text[i + 2 : end]) + "}")
                    i = end + 1
                    continue
            if ch == "_" and i + 1 < n and (
                text[i + 1].isalnum() or text[i + 1] in GREEK or _CJK_RE.match(text[i + 1])
            ):
                nxt = text[i + 1]
                if nxt.isascii():  # W_hh、L_ridge：一路吃到字母数字，ᵀ 之类留给上标分支
                    j = i + 1
                    while j < n and (text[j].isascii() and (text[j].isalnum() or text[j] == "_")):
                        j += 1
                    out.append(r"_{\mathrm{" + text[i + 1 : j] + "}}")
                    i = j
                    continue
                # 非 ASCII 下标：ε/β 要转成 \varepsilon，中文要包 \text，都不能越界吃掉后面的英文
                j = i + 1
                while j < n and (text[j] in GREEK or text[j] in PRECOMPOSED or _cjk_word(text[j])):
                    j += 1
                run = text[i + 1 : j]
                if any(_CJK_RE.match(c) for c in run):
                    out.append(r"_{\text{" + run + "}}")
                else:
                    out.append(r"_{\mathrm{" + to_latex(run) + "}}")
                i = j
                continue
            if ch == "\\":  # N\{j} 里的「集合差」，别处当反斜杠
                nxt = text[i + 1] if i + 1 < n else ""
                out.append(r"\setminus " if nxt in "{\" (" else r"\backslash ")
                i += 1
                continue
            if ch in GREEK:
                out.append(GREEK[ch])
                i += 1
                continue
            if ch in SYMBOLS:
                out.append(SYMBOLS[ch])
                i += 1
                continue
            if ch in _ASCII_SAFE:
                out.append(ch)
                i += 1
                continue
            if ch.isspace():
                out.append(" ")
                i += 1
                continue

            raise TexError(f"未收录的字符 {ch!r} (U+{ord(ch):04X})")

    latex = "".join(_space_after_macro(tok) for tok in out)
    latex = _FUNC_RE.sub(lambda m: FUNCTIONS[m.group(1)], latex)
    # 同一个原子挂两次上标（⊛ᶠˡᶦᵖ ᵀ 这种 Unicode 写法）LaTeX 会直接报
    # "Double superscript"，合并成一个 ^{flip\,T}
    latex = re.sub(r"\^\{([^{}]*)\}\s*\^\{([^{}]*)\}", lambda m: "^{" + m.group(1) + r"\," + m.group(2) + "}", latex)
    latex = re.sub(r"_\{([^{}]*)\}\s*_\{([^{}]*)\}", lambda m: "_{" + m.group(1) + r"\," + m.group(2) + "}", latex)
    return re.sub(r"\s{2,}", " ", latex).strip()


def _space_after_macro(token: str) -> str:
    """KaTeX 会把 \\cdotx 读成一个命令；给以字母结尾的命令补一个空格。"""
    if token.startswith("\\") and token[-1].isalpha():
        return token + " "
    return token


def to_latex_display(text: str) -> str:
    """多行公式折成 aligned；单行原样返回。"""
    parts = [to_latex(line) for line in split_lines(text)]
    if len(parts) == 1:
        return parts[0]
    return r"\begin{aligned}" + r"\\ ".join("&& " + p for p in parts) + r"\end{aligned}"
