import re
from pathlib import Path
from typing import Dict, Any, Optional
from graft.graph import CodebaseGraph

from .prompts import GRAFT_SYSTEM_INSTRUCTION

def load_senior_engineering_rules() -> str:
    """Tự động tải bộ quy tắc kỹ sư cao cấp từ file SENIOR_ENGINEERING_RULES.md."""
    possible_paths = [
        Path(__file__).parent.parent / "rules" / "SENIOR_ENGINEERING_RULES.md",
        Path(__file__).parent.parent / "SENIOR_ENGINEERING_RULES.md",
    ]
    for p in possible_paths:
        if p.exists():
            try:
                return p.read_text(encoding="utf-8", errors="replace").strip()
            except Exception:
                pass
    return ""

def load_project_custom_rules(project_dir: Optional[str] = None) -> str:
    """Tự động tải các quy tắc riêng của dự án người dùng (.cursorrules, CLAUDE.md, AGENTS.md, v.v.)."""
    if not project_dir:
        return ""
    pdir = Path(project_dir)
    if not pdir.exists():
        return ""

    rule_files = [
        ".cursorrules",
        "CLAUDE.md",
        "AGENTS.md",
        "RULES.md",
        ".cursor/rules/main.mdc"
    ]
    custom_rules = []
    for rf in rule_files:
        rpath = pdir / rf
        if rpath.exists() and rpath.is_file():
            try:
                txt = rpath.read_text(encoding="utf-8", errors="replace").strip()
                if txt:
                    custom_rules.append(f"=== PROJECT CONVENTIONS ({rf}) ===\n{txt}")
            except Exception:
                pass

    # Quét thêm các rule .mdc trong .cursor/rules/
    cursor_dir = pdir / ".cursor" / "rules"
    if cursor_dir.is_dir():
        for mdc in cursor_dir.glob("*.mdc"):
            try:
                txt = mdc.read_text(encoding="utf-8", errors="replace").strip()
                if txt:
                    custom_rules.append(f"=== CURSOR PROJECT CONVENTIONS ({mdc.name}) ===\n{txt}")
            except Exception:
                pass

    if custom_rules:
        return "\n\n" + "\n\n".join(custom_rules)
    return ""

def get_system_instruction(project_dir: Optional[str] = None) -> str:
    """Kết hợp chỉ dẫn hệ thống cơ sở với bộ quy tắc Senior Engineering và quy tắc riêng của dự án."""
    base = GRAFT_SYSTEM_INSTRUCTION
    senior_rules = load_senior_engineering_rules()
    project_rules = load_project_custom_rules(project_dir)

    combined = base
    if senior_rules:
        combined += f"\n\n{senior_rules}"
    if project_rules:
        combined += f"\n\n{project_rules}"
    return combined

def build_graft_prompt(task: str, graph: CodebaseGraph, target_file: Optional[str] = None, project_dir: Optional[str] = None) -> str:
    summary = graph.get_summary()
    
    doctor_section = ""
    if project_dir:
        try:
            from .environment_inspector import EnvironmentInspector
            inspection = EnvironmentInspector.inspect_project(project_dir)
            doctor_section = ("=== ENVIRONMENT REPORT (REFERENCE DATA; VERIFY RECOMMENDATIONS) ===\n"
                              + EnvironmentInspector.format_markdown_report(inspection) + "\n\n")
        except Exception as e:
            doctor_section = f"<!-- Environment inspection unavailable: {e} -->\n\n"

    prompt = f"""{doctor_section}=== CODEBASE SYMBOL GRAPH ===
Total indexed files: {summary['total_files']}
Total AST symbols: {summary['total_symbols']}

=== INDEXED PROJECT SYMBOLS ===
"""
    count = 0
    for f in summary["files"]:
        if target_file and target_file != f["path"]:
            continue
        prompt += f"\nFile: `{f['path']}` ({f['lines']} lines)\n"
        for s in f["symbols"]:
            args = f"({', '.join(s['args'])})" if s["args"] else ""
            parent = f" [Class: {s['parent']}]" if s["parent"] else ""
            prompt += f"  - [{s['type'].upper()}] {s['name']}{args} (L{s['line']}-L{s['end_line']}){parent}\n"
        count += 1
        if count >= 30:
            prompt += f"\n... {len(summary['files']) - count} more indexed files.\n"
            break

    # 1. Tự động nạp mã nguồn cho dự án nhỏ (Small project auto codebase injection)
    # Nếu dự án có <= 8 tệp và tổng số dòng code <= 1800 dòng:
    # Nạp toàn bộ mã nguồn thực tế của các tệp vào prompt!
    total_files = len(graph.files)
    total_lines = sum(f.total_lines for f in graph.files.values()) if graph.files else 0

    injected_files = set()
    source_sections = []

    if 0 < total_files <= 8 and total_lines <= 1800:
        source_sections.append(
            "\n=== FULL INDEXED CODEBASE SOURCE ===\n"
            "(Source for all indexed files in this small project is provided. "
            "Read it before inferring behavior; unindexed files may still exist.):\n"
        )
        for fpath, fast in sorted(graph.files.items()):
            ext = Path(fpath).suffix.lstrip(".") or "text"
            content = fast.raw_content or ""
            source_sections.append(f"File: `{fpath}` ({fast.total_lines} lines):\n```{ext}\n{content}\n```\n")
            injected_files.add(fpath)
    else:
        # Dự án lớn hơn: Trích xuất các tệp liên quan thông minh (Smart Relevant Files Resolver)
        relevant_files = []
        task_lower = task.lower()
        words = [w for w in re.findall(r'[a-zA-Z0-9_]+', task_lower) if len(w) >= 3]

        for fpath, fast in graph.files.items():
            if target_file and fpath == target_file:
                continue
            stem = Path(fpath).stem.lower()
            name = Path(fpath).name.lower()
            score = 0
            if name in task_lower or fpath.lower() in task_lower:
                score += 10
            elif stem in task_lower:
                score += 6
            else:
                for w in words:
                    if w in stem:
                        score += 3
                    elif w in (fast.raw_content or "")[:2000].lower():
                        score += 1

            if score > 0:
                relevant_files.append((score, fpath, fast))

        relevant_files.sort(key=lambda x: x[0], reverse=True)
        if relevant_files:
            source_sections.append(
                "\n=== RELEVANT SOURCE FILES ===\n"
                "(Read this source before analysis or edits. Retrieve missing context if needed.):\n"
            )
            for _, fpath, fast in relevant_files[:4]:
                ext = Path(fpath).suffix.lstrip(".") or "text"
                content = fast.raw_content or ""
                snippet = content[:5000]
                if len(content) > 5000:
                    snippet += "\n[TRUNCATED: request the full file before editing unseen content.]"
                source_sections.append(f"File: `{fpath}` ({fast.total_lines} lines):\n```{ext}\n{snippet}\n```\n")
                injected_files.add(fpath)

    if target_file and target_file in graph.files and target_file not in injected_files:
        file_obj = graph.files.get(target_file)
        if file_obj and file_obj.raw_content:
            ext = Path(target_file).suffix.lstrip(".") or "text"
            target_source = file_obj.raw_content[:8000]
            if len(file_obj.raw_content) > 8000:
                target_source += "\n[TRUNCATED: request the full file before editing unseen content.]"
            source_sections.append(f"""\n=== TARGET FILE SOURCE ({target_file}) ===
```{ext}
{target_source}
```
""")

    code_context = "".join(source_sections)

    prompt += f"""{code_context}
=== USER REQUEST ===
{task}

Address the requested outcome using the supplied evidence. Retrieve missing source before dependent edits.
For an implementation request, prepare focused action blocks and relevant verification; for a question,
answer directly. Report pending actions accurately and do not claim unobserved results.
"""
    return prompt
