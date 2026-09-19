import ast
import re
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field

@dataclass
class ASTSymbol:
    name: str
    symbol_type: str  # "function", "class", "method", "import", "variable"
    start_line: int
    end_line: int
    docstring: Optional[str] = None
    args: List[str] = field(default_factory=list)
    decorators: List[str] = field(default_factory=list)
    parent: Optional[str] = None
    source_slice: Optional[str] = None

@dataclass
class FileAST:
    file_path: str
    symbols: List[ASTSymbol] = field(default_factory=list)
    imports: List[str] = field(default_factory=list)
    total_lines: int = 0
    raw_content: str = ""

    def get_symbol(self, name: str, parent: Optional[str] = None) -> Optional[ASTSymbol]:
        for sym in self.symbols:
            if sym.name == name:
                if parent is None or sym.parent == parent:
                    return sym
        return None

def parse_python_ast(code: str, file_path: str = "file.py") -> FileAST:
    code = code.lstrip("\ufeff")
    lines = code.splitlines()
    res = FileAST(file_path=file_path, total_lines=len(lines), raw_content=code)
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return res

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            doc = ast.get_docstring(node)
            args = [a.arg for a in node.args.args]
            decorators = [ast.unparse(d) if hasattr(ast, 'unparse') else 'decorator' for d in node.decorator_list]
            start = node.lineno
            end = getattr(node, 'end_lineno', start)
            source_slice = "\n".join(lines[start - 1:end])
            res.symbols.append(ASTSymbol(
                name=node.name,
                symbol_type="function",
                start_line=start,
                end_line=end,
                docstring=doc,
                args=args,
                decorators=decorators,
                source_slice=source_slice
            ))
        elif isinstance(node, ast.ClassDef):
            c_doc = ast.get_docstring(node)
            c_start = node.lineno
            c_end = getattr(node, 'end_lineno', c_start)
            c_slice = "\n".join(lines[c_start - 1:c_end])
            res.symbols.append(ASTSymbol(
                name=node.name,
                symbol_type="class",
                start_line=c_start,
                end_line=c_end,
                docstring=c_doc,
                source_slice=c_slice
            ))
            # Quét các method bên trong class
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    m_doc = ast.get_docstring(item)
                    m_args = [a.arg for a in item.args.args]
                    m_start = item.lineno
                    m_end = getattr(item, 'end_lineno', m_start)
                    m_slice = "\n".join(lines[m_start - 1:m_end])
                    res.symbols.append(ASTSymbol(
                        name=item.name,
                        symbol_type="method",
                        start_line=m_start,
                        end_line=m_end,
                        docstring=m_doc,
                        args=m_args,
                        parent=node.name,
                        source_slice=m_slice
                    ))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                res.imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            names = [a.name for a in node.names]
            res.imports.append(f"{mod}:{','.join(names)}")

    return res

def parse_generic_symbols(code: str, file_path: str) -> FileAST:
    code = code.lstrip("\ufeff")
    lines = code.splitlines()
    res = FileAST(file_path=file_path, total_lines=len(lines), raw_content=code)
    
    # Regex hỗ trợ cả PHP, JS, TS, Go, Java, C#, Python
    func_pattern = re.compile(
        r'^(?:[ \t]*(?:public|private|protected|static|abstract|final|async|export)\s+)*function\s+([a-zA-Z0-9_]+)\s*\(([^)]*)\)',
        re.MULTILINE
    )
    class_pattern = re.compile(
        r'^(?:[ \t]*(?:abstract|final|export)\s+)*class\s+([a-zA-Z0-9_]+)',
        re.MULTILINE
    )

    current_class = None
    for idx, line in enumerate(lines, 1):
        m_class = class_pattern.search(line)
        if m_class:
            current_class = m_class.group(1)
            res.symbols.append(ASTSymbol(
                name=current_class,
                symbol_type="class",
                start_line=idx,
                end_line=idx
            ))
            continue

        m_func = func_pattern.search(line)
        if m_func:
            fn_name = m_func.group(1)
            args = [a.strip() for a in m_func.group(2).split(',') if a.strip()]
            sym_type = "method" if current_class else "function"
            res.symbols.append(ASTSymbol(
                name=fn_name,
                symbol_type=sym_type,
                start_line=idx,
                end_line=idx,
                args=args,
                parent=current_class
            ))

    return res

def parse_code_to_ast(code: str, file_path: str = "file.py") -> FileAST:
    if file_path.endswith(".py"):
        return parse_python_ast(code, file_path)
    return parse_generic_symbols(code, file_path)
