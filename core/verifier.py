import py_compile
import tempfile
import os
from typing import Tuple

def verify_code(file_path: str, code: str) -> Tuple[bool, str]:
    """
    Kiểm tra tính hợp lệ cú pháp của code vừa ghép trước khi lưu.
    """
    ext = os.path.splitext(file_path)[-1].lower()
    if ext == ".py":
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", encoding="utf-8", delete=False) as tmp:
            tmp.write(code)
            tmp_name = tmp.name

        try:
            py_compile.compile(tmp_name, doraise=True)
            return True, "Cú pháp Python hợp lệ (Syntax Passed)."
        except py_compile.PyCompileError as e:
            return False, f"Lỗi cú pháp Python:\n{e}"
        finally:
            if os.path.exists(tmp_name):
                os.remove(tmp_name)

    return True, "Bỏ qua kiểm tra (Ngôn ngữ không hỗ trợ verify tự động)."
