import os
from pathlib import Path
from typing import Dict, List, Optional, Any
from .parser import FileAST, parse_code_to_ast, ASTSymbol

class CodebaseGraph:
    """
    Đồ thị biểu tượng & phụ thuộc của toàn bộ dự án (Codebase Symbol Graph).
    """
    def __init__(self, root_dir: str):
        self.root_dir = Path(root_dir).resolve()
        self.files: Dict[str, FileAST] = {}
        self.symbol_index: Dict[str, List[Dict[str, Any]]] = {}

    def scan(self, max_files: int = 200):
        self.files.clear()
        self.symbol_index.clear()

        ignored = {".git", "__pycache__", "node_modules", ".venv", "venv", "dist", "build", ".idea", ".vscode"}
        extensions = {".py", ".ts", ".js", ".jsx", ".tsx", ".go", ".php", ".json", ".html"}

        count = 0
        for root, dirs, filenames in os.walk(self.root_dir):
            dirs[:] = [d for d in dirs if d not in ignored and not d.startswith(".")]
            for fname in filenames:
                ext = Path(fname).suffix.lower()
                if ext in extensions:
                    full_path = Path(root) / fname
                    rel_path = str(full_path.relative_to(self.root_dir)).replace("\\", "/")
                    try:
                        content = full_path.read_text(encoding="utf-8-sig", errors="replace")
                        fast = parse_code_to_ast(content, rel_path)
                        self.files[rel_path] = fast

                        for sym in fast.symbols:
                            if sym.name not in self.symbol_index:
                                self.symbol_index[sym.name] = []
                            self.symbol_index[sym.name].append({
                                "file": rel_path,
                                "type": sym.symbol_type,
                                "line": sym.start_line,
                                "parent": sym.parent,
                                "args": sym.args,
                                "doc": sym.docstring
                            })

                        count += 1
                        if count >= max_files:
                            break
                    except Exception as e:
                        pass
            if count >= max_files:
                break

    def find_symbol(self, name: str) -> List[dict]:
        return self.symbol_index.get(name, [])

    def get_summary(self) -> Dict[str, Any]:
        """
        Trả về tóm tắt chi tiết cấu trúc các tệp và biểu tượng AST.
        """
        total_symbols = sum(len(f.symbols) for f in self.files.values())
        file_list = []
        for fpath, fast in sorted(self.files.items()):
            syms = []
            for s in fast.symbols:
                syms.append({
                    "name": s.name,
                    "type": s.symbol_type,
                    "line": s.start_line,
                    "end_line": s.end_line,
                    "parent": s.parent,
                    "args": s.args
                })
            file_list.append({
                "path": fpath,
                "lines": fast.total_lines,
                "symbols": syms
            })
        return {
            "total_files": len(self.files),
            "total_symbols": total_symbols,
            "files": file_list
        }

    def get_compact_summary(self) -> str:
        """
        Tạo bản đồ ngữ cảnh siêu tối giản để gửi cho AI (tiết kiệm token).
        """
        parts = [f"📊 **BẢN ĐỒ BIỂU TƯỢNG DỰ ÁN (Codebase AST Graph)** - {len(self.files)} files:"]
        for fpath, fast in sorted(self.files.items()):
            symbols_str = []
            for s in fast.symbols:
                if s.symbol_type == "class":
                    symbols_str.append(f"Class {s.name}")
                elif s.symbol_type == "function":
                    args = ", ".join(s.args)
                    symbols_str.append(f"def {s.name}({args})")
                elif s.symbol_type == "method":
                    symbols_str.append(f"  └─ {s.parent}.{s.name}()")

            sym_preview = "; ".join(symbols_str[:8]) if symbols_str else "(No symbols)"
            if len(symbols_str) > 8:
                sym_preview += f" ...và {len(symbols_str) - 8} hàm khác"
            parts.append(f"- `{fpath}`: {sym_preview}")

        return "\n".join(parts)
