"""Text sanitization and formatting utilities for Graft Code Agent."""

import re


def sanitize_latex(text: str) -> str:
    """Chuyển đổi cú pháp LaTeX math và các đơn vị thường gặp thành văn bản Unicode thuần túy.

    Xử lý:
    - Nhiệt độ / độ: $25^\\circ\\text{C}$ -> 25°C, 32^\\circ\\text{C}$ -> 32°C, 35^\\circ C -> 35°C
    - Đơn vị trong \\text{...}: $10 - 15\\text{ km/h}$ -> 10 - 15 km/h, $15\\text{h}00 - 18\\text{h}30$ -> 15h00 - 18h30
    - Phần trăm & dải số: $75% - 92%$ -> 75% - 92%
    - Ký hiệu toán học: \\times -> ×, \\approx -> ≈, \\pm -> ±, \\le/\\leq -> ≤, \\ge/\\geq -> ≥, \\neq -> ≠, \\cdot -> ·, \\sqrt -> √, \\frac{a}{b} -> a/b
    - Số mũ đơn giản: ^2 / ^{2} -> ², ^3 / ^{3} -> ³
    - Xóa các khối math delimiters: $$...$$, \\[...\\], \\(...\\), $...$ mà không làm ảnh hưởng đến giá tiền ($50) hay code block.
    """
    if not text:
        return text

    # 1. Bảo vệ các khối code block (fenced & inline)
    code_blocks = []

    def save_code(m):
        code_blocks.append(m.group(0))
        return f"\x00CODE_BLOCK_{len(code_blocks)-1}\x00"

    t = re.sub(r'(```[\s\S]*?```|`[^`\n]+`)', save_code, text)

    # 2. Xử lý nhiệt độ và độ: ^\circ\text{C}, ^{\circ}\text{C}, ^\circ C, \degree C
    t = re.sub(r'(?:\^\\circ|\^{\\circ}|\\degree)\s*(?:\\text\s*\{([A-Za-z]+)\}|([A-Za-z]))', r'°\1\2', t)
    t = re.sub(r'(?:\^\\circ|\^{\\circ}|\\degree)', '°', t)

    # 3. Thẻ text & định dạng phông toán: \text{...}, \mathrm{...}, \mathbf{...}, \mathit{...}
    t = re.sub(r'\\(?:text|mathrm|mathbf|mathit|operatorname)\s*\{([^}]*)\}', r'\1', t)

    # 4. Ký hiệu toán học & đơn vị phổ biến
    t = re.sub(r'\\times\b', '×', t)
    t = re.sub(r'\\approx\b', '≈', t)
    t = re.sub(r'\\pm\b', '±', t)
    t = re.sub(r'\\(?:le|leq)\b', '≤', t)
    t = re.sub(r'\\(?:ge|geq)\b', '≥', t)
    t = re.sub(r'\\(?:ne|neq)\b', '≠', t)
    t = re.sub(r'\\cdot\b', '·', t)
    t = re.sub(r'\\sim\b', '~', t)
    t = re.sub(r'\\(?:to|rightarrow)\b', '→', t)
    t = re.sub(r'\\leftarrow\b', '←', t)
    t = re.sub(r'\\leftrightarrow\b', '↔', t)
    t = re.sub(r'\\Rightarrow\b', '⇒', t)
    t = re.sub(r'\\mu\b', 'µ', t)
    t = re.sub(r'\\pi\b', 'π', t)
    t = re.sub(r'\\alpha\b', 'α', t)
    t = re.sub(r'\\beta\b', 'β', t)
    t = re.sub(r'\\gamma\b', 'γ', t)
    t = re.sub(r'\\theta\b', 'θ', t)
    t = re.sub(r'\\lambda\b', 'λ', t)
    t = re.sub(r'\\sigma\b', 'σ', t)
    t = re.sub(r'\\omega\b', 'ω', t)
    t = re.sub(r'\\Delta\b', 'Δ', t)
    t = re.sub(r'\\infty\b', '∞', t)

    # Khoảng trắng LaTeX: \quad, \qquad, \, \; \: \!
    t = re.sub(r'\\(?:quad|qquad)\b', ' ', t)
    t = re.sub(r'\\[,;:!]', ' ', t)

    # Phân số & căn: \frac{a}{b} -> a/b, \sqrt{x} -> √(x)
    t = re.sub(r'\\frac\s*\{([^}]+)\}\s*\{([^}]+)\}', r'\1/\2', t)
    t = re.sub(r'\\sqrt\s*\{([^}]+)\}', r'√(\1)', t)
    t = re.sub(r'\\sqrt\b', '√', t)

    # Ngoặc \left( \right)
    t = re.sub(r'\\left\(', '(', t)
    t = re.sub(r'\\right\)', ')', t)
    t = re.sub(r'\\left\[', '[', t)
    t = re.sub(r'\\right\]', ']', t)
    t = re.sub(r'\\left\{', '{', t)
    t = re.sub(r'\\right\}', '}', t)

    # Số mũ đơn giản: ^2 -> ², ^3 -> ³
    t = re.sub(r'(?<=\w)\^(?:2|\{2\})\b', '²', t)
    t = re.sub(r'(?<=\w)\^(?:3|\{3\})\b', '³', t)

    # Ký tự escape đặc biệt trong LaTeX: \%, \&, \_, \#, \{, \}
    t = re.sub(r'\\([%$&_#{}])', r'\1', t)

    # 5. Loại bỏ cặp bao toán học: $$...$$, \[...\], \(...\)
    t = re.sub(r'\$\$(.*?)\$\$', r'\1', t, flags=re.DOTALL)
    t = re.sub(r'\\\[(.*?)\\\]', r'\1', t, flags=re.DOTALL)
    t = re.sub(r'\\\((.*?)\\\)', r'\1', t, flags=re.DOTALL)

    # 6. Loại bỏ cặp $...$ inline math theo chuẩn Markdown
    def clean_inline_math(match):
        inner = match.group(1)
        # Nếu chứa ký hiệu toán học / đơn vị / độ / phần trăm / thời gian
        if any(ch in inner for ch in (
            '\\', '^', '_', '{', '}', '°', '℃', '℉', '%', '≤', '≥', '≈',
            '≠', '±', '×', '·', '²', '³', 'µ', 'π', 'α', 'β', 'γ', 'θ',
            'λ', 'σ', 'ω', 'Δ', '∞', '√'
        )):
            return inner
        # Nếu là dải số, giờ giấc hoặc đơn vị: ví dụ "10 - 15 km/h", "15h00 - 18h30", "75 - 92"
        if re.search(r'^\s*\d+.*(?:h\d+|km/h|m/s|kg|g|m|cm|mm|\b\d+\s*[-–~]\s*\d+)', inner, re.IGNORECASE):
            return inner
        # Nếu là biểu thức có toán tử: = + - * / < >
        if re.search(r'[=+*/<>]', inner) and re.search(r'\d|[a-zA-Z]', inner):
            return inner
        return match.group(0)

    t = re.sub(r'(?<!\\)\$([^\s$\n](?:[^$\n]*?[^\s$\n])?)(?<!\\)\$', clean_inline_math, t)

    # 7. Dọn dẹp ký tự $ lẻ còn sót lại quanh số, đơn vị, khoảng giá trị
    # (Trường hợp AI quên mở $ như "- 32^\circ\text{C}$" -> "- 32°C$")
    t = re.sub(r'(?<=[0-9A-Za-z°%℃℉])\$(?=[,\.;:\s\)]|$)', '', t)

    # 8. Khôi phục lại các khối code
    for idx, cb in enumerate(code_blocks):
        t = t.replace(f"\x00CODE_BLOCK_{idx}\x00", cb)

    return t
