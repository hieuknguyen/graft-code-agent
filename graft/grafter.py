import re
from typing import Tuple, Optional
from .parser import parse_code_to_ast

class Grafter:
    """
    Thuật toán phẫu thuật cấy ghép mã nguồn (Surgical Code Grafting):
    - Định vị chính xác Node/Hàm/Class trong cây cú pháp
    - Thay thế node hoặc cấy ghép hàm mới vào đúng vị trí
    - Giữ nguyên 100% định dạng thụt lề, comment và các hàm xung quanh
    """

    @staticmethod
    def graft_replace_symbol(
        source_code: str,
        symbol_name: str,
        new_code: str,
        parent_class: Optional[str] = None,
        file_path: str = "file.py"
    ) -> Tuple[bool, str, str]:
        """
        Thay thế trúng đích 1 hàm hoặc class bằng code mới.
        Trả về (thành công, code_mới, thông_báo)
        """
        ast_res = parse_code_to_ast(source_code, file_path)
        sym = ast_res.get_symbol(symbol_name, parent=parent_class)
        if not sym:
            # Hỗ trợ tệp kịch bản tuần tự (procedural script như ketnoi.php, config.php) hoặc symbol target chung
            is_procedural = len(ast_res.symbols) == 0
            is_generic = (not symbol_name) or symbol_name.lower() in (
                "all", "file", "root", "script", "global", "none", "db", "database",
                "ketnoi", "ketnoi_db", "config", "connection", "conn"
            )
            if is_procedural or is_generic:
                clean_new = new_code.strip()
                # Trường hợp A: Code thay thế hoàn chỉnh (bắt đầu bằng <?php hoặc nhiều dòng tương đương file gốc)
                if clean_new.startswith("<?php") or len(clean_new.splitlines()) >= len(source_code.splitlines()) - 1:
                    return True, clean_new + "\n", f"Đã cấy ghép thay thế nội dung tệp kịch bản '{file_path}'."

                # Trường hợp B: Câu lệnh bổ sung trong tệp PHP (ví dụ: mysqli_set_charset($conn, 'utf8mb4');)
                if file_path.lower().endswith(".php") or "<?php" in source_code:
                    if "?>" in source_code:
                        parts = source_code.rsplit("?>", 1)
                        res = parts[0].rstrip() + "\n    " + clean_new + "\n?>" + parts[1]
                        return True, res, f"Đã cấy ghép câu lệnh mới vào trước thẻ '?>' trong tệp PHP '{file_path}'."
                    else:
                        res = source_code.rstrip() + "\n    " + clean_new + "\n"
                        return True, res, f"Đã cấy ghép câu lệnh mới vào tệp PHP '{file_path}'."
                else:
                    res = source_code.rstrip() + "\n" + clean_new + "\n"
                    return True, res, f"Đã cấy ghép câu lệnh vào tệp '{file_path}'."

            return False, source_code, f"Không tìm thấy biểu tượng '{symbol_name}' trong AST."

        lines = source_code.splitlines(keepends=True)
        orig_first_line = lines[sym.start_line - 1] if sym.start_line - 1 < len(lines) else ""
        orig_indent = re.match(r"^(\s*)", orig_first_line).group(1)

        # Chuẩn hóa thụt lề cho new_code
        new_lines = new_code.splitlines()
        first_line_new = new_lines[0] if new_lines else ""
        new_indent = re.match(r"^(\s*)", first_line_new).group(1) if new_lines else ""

        adjusted_lines = []
        for line in new_lines:
            if line.startswith(new_indent) and len(new_indent) > 0:
                adjusted_lines.append(orig_indent + line[len(new_indent):] + "\n")
            else:
                adjusted_lines.append(orig_indent + line + "\n")

        # Thay thế đoạn dòng từ [start_line - 1 : end_line]
        before = lines[:sym.start_line - 1]
        after = lines[sym.end_line:]
        result_code = "".join(before) + "".join(adjusted_lines) + "".join(after)

        return True, result_code, f"Đã cấy ghép thành công thay thế symbol '{symbol_name}'."

    @staticmethod
    def graft_insert_symbol(
        source_code: str,
        new_code: str,
        parent_class: Optional[str] = None,
        file_path: str = "file.py"
    ) -> Tuple[bool, str, str]:
        """
        Cấy ghép thêm một hàm hoặc class mới vào file hoặc bên trong một class.
        """
        ast_res = parse_code_to_ast(source_code, file_path)
        lines = source_code.splitlines(keepends=True)

        if parent_class:
            c_sym = ast_res.get_symbol(parent_class)
            if not c_sym or c_sym.symbol_type != "class":
                return False, source_code, f"Không tìm thấy class '{parent_class}' để chèn method."

            # Chèn vào cuối class (ngay trước end_line)
            insert_idx = c_sym.end_line
            # Xác định thụt lề class + 4 spaces
            c_line = lines[c_sym.start_line - 1]
            c_indent = re.match(r"^(\s*)", c_line).group(1)
            method_indent = c_indent + "    "

            adjusted_new = []
            for l in new_code.splitlines():
                adjusted_new.append(method_indent + l.lstrip() + "\n")

            result = "".join(lines[:insert_idx]) + "\n" + "".join(adjusted_new) + "".join(lines[insert_idx:])
            return True, result, f"Đã cấy ghép thêm method vào class '{parent_class}'."
        else:
            # Nếu là file PHP (hoặc có chứa thẻ <?php)
            is_php = file_path.lower().endswith(".php") or "<?php" in source_code
            if is_php:
                import re as _re
                clean_new = new_code.strip()
                # Loại bỏ <?php và ?> nếu LLM đã bọc ngoài
                clean_new = _re.sub(r'^\s*<\?php\s*', '', clean_new, flags=_re.IGNORECASE)
                clean_new = _re.sub(r'\s*\?>\s*$', '', clean_new)

                lines = source_code.splitlines(keepends=True)
                insert_idx = -1

                # Nếu là file procedural PHP không chứa hàm/lớp nào (như ketnoi.php)
                if len(ast_res.symbols) == 0:
                    for idx, line in enumerate(lines):
                        if "?>" in line:
                            insert_idx = idx
                            break
                    if insert_idx != -1:
                        lines.insert(insert_idx, "    " + clean_new + "\n")
                        return True, "".join(lines), "Đã cấy ghép câu lệnh vào tệp PHP kịch bản."

                in_php_block = False
                for idx, line in enumerate(lines):
                    if "<?php" in line:
                        in_php_block = True
                        insert_idx = idx + 1
                    elif in_php_block:
                        if "?>" in line:
                            insert_idx = idx
                            break
                        elif line.strip().startswith(("require", "include", "use ", "namespace ")):
                            insert_idx = idx + 1
                        elif line.strip() == "" or line.strip().startswith(("//", "/*", "*")):
                            continue
                        else:
                            insert_idx = idx
                            break

                if insert_idx != -1 and insert_idx <= len(lines):
                    lines.insert(insert_idx, "\n" + clean_new + "\n\n")
                    return True, "".join(lines), "Đã cấy ghép hàm mới vào khối <?php đầu tệp."
                else:
                    result = "<?php\n" + clean_new + "\n?>\n\n" + source_code
                    return True, result, "Đã cấy ghép hàm mới vào đầu file PHP."
            else:
                # Chèn vào cuối file (cho Python, JS, Go...)
                result = source_code.rstrip() + "\n\n" + new_code.strip() + "\n"
                return True, result, "Đã cấy ghép hàm mới vào cuối file."

    @staticmethod
    def ensure_import(source_code: str, import_stmt: str) -> str:
        """
        Bảo đảm câu lệnh import tồn tại ở đầu file.
        """
        if import_stmt.strip() in source_code:
            return source_code

        lines = source_code.splitlines(keepends=True)
        # Tìm vị trí import cuối cùng
        last_import_idx = 0
        for idx, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("import ") or stripped.startswith("from "):
                last_import_idx = idx + 1

        lines.insert(last_import_idx, import_stmt.strip() + "\n")
        return "".join(lines)
