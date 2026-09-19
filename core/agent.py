import os
import re
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
from config import AppConfig
from graft.graph import CodebaseGraph
from graft.grafter import Grafter
from graft.diff_utils import generate_unified_diff, count_diff_stats
from .gateway_client import GatewayClient
from .context_builder import GRAFT_SYSTEM_INSTRUCTION, build_graft_prompt, get_system_instruction
from .verifier import verify_code
from .gemini_agent import GeminiCodingAgent
from .tool_runtime import ToolRuntime, ToolRuntimeError

class GraftAgent:
    def __init__(self, config: AppConfig, root_dir: str):
        self.config = config
        self.root_dir = Path(root_dir).resolve()
        self.graph = CodebaseGraph(str(self.root_dir))
        self.client = GatewayClient(config)
        # Every frontend shares this boundary.  Gemini only receives the tool
        # surface, never a raw Path or a direct shell handle.
        self.runtime = ToolRuntime(str(self.root_dir))
        self.history_backups: List[Dict[str, Any]] = []

    def scan(self):
        self.graph.scan()

    def _plan_with_gemini(self, task: str, target_file: Optional[str], images: Optional[List[str]]) -> Dict[str, Any]:
        """Convert approved-pending Gemini proposals to the existing UI shape."""
        result = GeminiCodingAgent(self.config, self.runtime).run(task, target_file=target_file, images=images)
        if not result.get("success"):
            return result

        actions: List[Dict[str, Any]] = []
        create_files: List[Dict[str, Any]] = []
        delete_files: List[Dict[str, Any]] = []
        commands: List[Dict[str, Any]] = []
        for proposal_id in result.get("proposal_ids", []):
            ui = self.runtime.proposal_for_ui(proposal_id)
            if not ui.ok:
                continue
            proposal = ui.data
            kind = proposal.get("kind")
            if kind == "write":
                valid, verify_msg = verify_code(proposal["file"], proposal["new_code"])
                if proposal.get("operation") == "create":
                    create_files.append({
                        "file": proposal["file"],
                        "code": proposal["new_code"],
                        "proposal_id": proposal_id,
                        "success": valid,
                        "verify_msg": verify_msg,
                        "description": proposal.get("description", ""),
                    })
                else:
                    actions.append({
                        "file": proposal["file"],
                        "success": valid,
                        "msg": proposal.get("description") or "Đã chuẩn bị thay đổi từ Gemini; chờ xác nhận để ghi file.",
                        "diff": proposal["diff"],
                        "original_code": proposal["original_code"],
                        "new_code": proposal["new_code"],
                        "proposal_id": proposal_id,
                        "verified": valid,
                        "verify_msg": verify_msg,
                        "action": {"action": "WRITE"},
                    })
            elif kind == "delete":
                delete_files.append({
                    "file": proposal["file"],
                    "reason": proposal.get("reason", ""),
                    "proposal_id": proposal_id,
                })
            elif kind == "command":
                commands.append({
                    "command": proposal["command"],
                    "description": proposal.get("description", ""),
                    "proposal_id": proposal_id,
                    "shell": proposal.get("shell", "cmd"),
                    "risk": proposal.get("risk", "normal"),
                    "cwd": proposal.get("cwd", ""),
                    "timeout_seconds": proposal.get("timeout_seconds", 120),
                })

        return {
            "success": True,
            "response": result.get("response", ""),
            "raw_response": result.get("response", ""),
            "actions": actions,
            "create_files": create_files,
            "delete_files": delete_files,
            "commands": commands,
            "tokens": result.get("tokens", {}),
        }

    def parse_all_actions(self, ai_text: str) -> Dict[str, List[Dict[str, Any]]]:
        graft_actions = []
        create_actions = []
        delete_actions = []
        command_actions = []

        # 1. Parse <<<GRAFT_ACTION ... >>>
        graft_pattern = re.compile(r'<<<GRAFT_ACTION(.*?)>>>', re.DOTALL)
        for raw_block in graft_pattern.findall(ai_text):
            action_type_m = re.search(r'Action:[ \t]*(REPLACE|INSERT|ENSURE_IMPORT)', raw_block, re.IGNORECASE)
            file_m = re.search(r'File:[ \t]*([^\r\n]+)', raw_block)
            symbol_m = re.search(r'Symbol:[ \t]*([^\r\n]+)', raw_block)
            parent_m = re.search(r'Parent:[ \t]*([^\r\n]+)', raw_block)
            import_m = re.search(r'Import:[ \t]*([^\r\n]+)', raw_block)
            code_m = re.search(r'```(?:[a-zA-Z0-9_-]+)?\s*\n(.*?)```', raw_block, re.DOTALL)
            code = code_m.group(1).rstrip() if code_m else ""

            symbol_val = symbol_m.group(1).strip() if symbol_m else None
            parent_val = parent_m.group(1).strip() if parent_m else None
            import_val = import_m.group(1).strip() if import_m else None

            if parent_val and (parent_val.lower() in ("none", "null", "no", "") or parent_val.startswith("<")):
                parent_val = None
            if symbol_val and symbol_val.startswith("<"):
                symbol_val = None

            if action_type_m and file_m:
                graft_actions.append({
                    "action": action_type_m.group(1).upper(),
                    "file": file_m.group(1).strip().replace("`", ""),
                    "symbol": symbol_val,
                    "parent": parent_val,
                    "import": import_val,
                    "code": code
                })

        # 2. Parse <<<CREATE_FILE ... <<<END_CREATE_FILE
        create_pattern = re.compile(r'<<<CREATE_FILE(.*?)<<<END_CREATE_FILE', re.DOTALL)
        for raw_block in create_pattern.findall(ai_text):
            file_m = re.search(r'File:[ \t]*([^\r\n]+)', raw_block)
            code_m = re.search(r'```(?:[a-zA-Z0-9_-]+)?\s*\n(.*?)```', raw_block, re.DOTALL)
            if file_m and code_m:
                create_actions.append({
                    "file": file_m.group(1).strip().replace("`", ""),
                    "code": code_m.group(1).rstrip()
                })

        # 3. Parse <<<DELETE_FILE ... <<<END_DELETE_FILE
        delete_pattern = re.compile(r'<<<DELETE_FILE(.*?)<<<END_DELETE_FILE', re.DOTALL)
        for raw_block in delete_pattern.findall(ai_text):
            file_m = re.search(r'File:[ \t]*([^\r\n]+)', raw_block)
            reason_m = re.search(r'Reason:[ \t]*([^\r\n]+)', raw_block)
            if file_m:
                delete_actions.append({
                    "file": file_m.group(1).strip().replace("`", ""),
                    "reason": reason_m.group(1).strip() if reason_m else "Xóa theo yêu cầu"
                })

        # 4. Parse <<<RUN_COMMAND ... <<<END_RUN_COMMAND
        cmd_pattern = re.compile(r'<<<RUN_COMMAND(.*?)<<<END_RUN_COMMAND', re.DOTALL)
        for raw_block in cmd_pattern.findall(ai_text):
            cmd_m = re.search(r'Command:[ \t]*([^\r\n]+)', raw_block)
            desc_m = re.search(r'Description:[ \t]*([^\r\n]+)', raw_block)
            if cmd_m:
                command_actions.append({
                    "command": cmd_m.group(1).strip(),
                    "description": desc_m.group(1).strip() if desc_m else ""
                })

        # Fallback: Tự động trích xuất các lệnh terminal từ code block ```bash / ```sh nếu AI quên thẻ
        if not command_actions:
            sh_blocks = re.findall(r'```(?:bash|sh|shell|cmd|powershell)\s*\n(.*?)```', ai_text, re.DOTALL | re.IGNORECASE)
            for block in sh_blocks:
                for line in block.strip().splitlines():
                    clean_line = line.strip().lstrip("$").strip()
                    if clean_line and not clean_line.startswith("#") and not clean_line.startswith("//"):
                        command_actions.append({
                            "command": clean_line,
                            "description": "Lệnh trích xuất từ phản hồi của AI"
                        })

        return {
            "graft": graft_actions,
            "create": create_actions,
            "delete": delete_actions,
            "command": command_actions
        }

    def clean_ai_response(self, text: str) -> str:
        """Loại bỏ các block raw thẻ lệnh để chat hiển thị markdown thuần đẹp mắt."""
        t = re.sub(r'<<<GRAFT_ACTION.*?>>>', '', text, flags=re.DOTALL)
        t = re.sub(r'<<<CREATE_FILE.*?<<<END_CREATE_FILE', '', t, flags=re.DOTALL)
        t = re.sub(r'<<<DELETE_FILE.*?<<<END_DELETE_FILE', '', t, flags=re.DOTALL)
        t = re.sub(r'<<<RUN_COMMAND.*?<<<END_RUN_COMMAND', '', t, flags=re.DOTALL)
        return t.strip()

    def extract_context_snippets_from_text(self, text: str) -> str:
        """
        Tự động phân tích chuỗi văn bản (log terminal hoặc tin nhắn người dùng)
        để tìm ra các tệp mã nguồn và số dòng xảy ra lỗi, sau đó đọc nội dung
        thực tế của file và đưa vào ngữ cảnh cho AI quan sát trực tiếp!
        """
        if not text:
            return ""

        snippets = []
        seen_files = set()

        # 1. Tìm các mẫu lỗi PHP: "in ... on line XX" hoặc "in ...:XX"
        matches_php = re.findall(r'in\s+([a-zA-Z]:[\\/][^\r\n:]+\.php|[a-zA-Z0-9_./\\-]+\.php)(?:(?:\s+on\s+line\s+|:)(\d+))?', text, re.IGNORECASE)
        for fpath_raw, line_str in matches_php:
            fpath_clean = fpath_raw.strip().replace("\\", "/")
            line_num = int(line_str) if line_str and line_str.isdigit() else None
            self._add_file_snippet(fpath_clean, line_num, snippets, seen_files)

        # 2. Tìm các mẫu Python Traceback: File "...", line XX
        matches_py = re.findall(r'File\s+"([^"]+\.py)",\s+line\s+(\d+)', text)
        for fpath_raw, line_str in matches_py:
            fpath_clean = fpath_raw.strip().replace("\\", "/")
            line_num = int(line_str) if line_str and line_str.isdigit() else None
            self._add_file_snippet(fpath_clean, line_num, snippets, seen_files)

        # 3. Tìm các mẫu Node.js stack trace: at ... (path:line:col)
        matches_node = re.findall(r'at\s+(?:.*?\s+\()?([a-zA-Z]:[\\/][^\r\n:()]+\.[a-zA-Z0-9]+|[a-zA-Z0-9_./\\-]+\.[a-zA-Z0-9]+):(\d+)(?::\d+)?\)?', text)
        for fpath_raw, line_str in matches_node:
            fpath_clean = fpath_raw.strip().replace("\\", "/")
            line_num = int(line_str) if line_str and line_str.isdigit() else None
            self._add_file_snippet(fpath_clean, line_num, snippets, seen_files)

        # 4. Tìm các tệp mã nguồn cụ thể được nhắc tới trong văn bản
        file_mentions = re.findall(r'\b([a-zA-Z0-9_./\\-]+\.(?:php|py|js|ts|html|css|json|env|sql))\b', text, re.IGNORECASE)
        for fname in file_mentions:
            if fname.lower() not in seen_files and not fname.lower().endswith((".min.js", ".min.css")):
                self._add_file_snippet(fname, None, snippets, seen_files)

        if not snippets:
            return ""

        return "=== NỘI DUNG TỆP MÃ NGUỒN LIÊN QUAN TRỰC TIẾP ĐẾN LỖI (SOURCE FILE SNIPPETS) ===\n" + "\n".join(snippets) + "\n\n"

    def _add_file_snippet(self, fpath_str: str, line_num: Optional[int], snippets: list, seen_files: set):
        p = Path(fpath_str)
        fname = p.name.lower()
        if fname in seen_files:
            return

        resolved = None
        if p.is_absolute() and p.exists() and p.is_file():
            resolved = p
        else:
            cand = self.root_dir / p
            if cand.exists() and cand.is_file():
                resolved = cand
            else:
                for match in self.root_dir.rglob(p.name):
                    if match.is_file() and not any(part in (".git", "vendor", "node_modules", ".venv", "venv") for part in match.parts):
                        resolved = match
                        break

        if not resolved or not resolved.is_file():
            return

        seen_files.add(fname)
        try:
            rel_path = resolved.relative_to(self.root_dir).as_posix()
        except Exception:
            rel_path = resolved.name

        try:
            lines = resolved.read_text(encoding="utf-8-sig", errors="replace").splitlines()
            total = len(lines)
            ext = resolved.suffix.lstrip(".") or "text"

            snippet_str = f"📄 Tệp: `{rel_path}` (Tổng {total} dòng)\n"

            if total <= 180:
                snippet_str += f"```{ext}\n"
                for i, l in enumerate(lines, 1):
                    mark = " >>> " if (line_num and i == line_num) else "     "
                    snippet_str += f"{i:4d}{mark}| {l}\n"
                snippet_str += "```\n"
            else:
                snippet_str += f"[Dòng 1 - {min(15, total)} (Đầu tệp)]:\n```{ext}\n"
                for i in range(1, min(16, total + 1)):
                    snippet_str += f"{i:4d}     | {lines[i-1]}\n"
                snippet_str += "```\n"

                if line_num and line_num > 15:
                    start_l = max(16, line_num - 20)
                    end_l = min(total, line_num + 20)
                    snippet_str += f"[Đoạn mã quanh dòng lỗi {line_num} (Dòng {start_l} - {end_l})]:\n```{ext}\n"
                    for i in range(start_l, end_l + 1):
                        mark = " >>> " if i == line_num else "     "
                        snippet_str += f"{i:4d}{mark}| {lines[i-1]}\n"
                    snippet_str += "```\n"

            snippets.append(snippet_str)
        except Exception:
            pass

    def generate_expert_diagnostic_notes(self, text: str) -> str:
        """
        Tư duy chuyên gia (Senior Engineering Diagnostic Brain):
        Tự động phân tích các dấu hiệu đặc biệt trong log/yêu cầu và tạo các
        chỉ dẫn chẩn đoán chuyên sâu để AI không bao giờ bị phản xạ mù quáng.
        """
        if not text:
            return ""

        notes = []

        # 1. Phát hiện request Service Worker / Firebase từ trình duyệt
        if "firebase-messaging-sw.js" in text or "serviceworker" in text.lower():
            has_firebase_in_code = False
            try:
                for fpath_str, f_ast in self.graph.files.items():
                    if "firebase" in fpath_str.lower() or (f_ast.raw_content and "firebase" in f_ast.raw_content.lower()):
                        has_firebase_in_code = True
                        break
            except Exception:
                pass

            if not has_firebase_in_code:
                notes.append(
                    "⚠️ [CHẨN ĐOÁN CHUYÊN GIA VỀ /firebase-messaging-sw.js]:\n"
                    "Request 404 này hoàn toàn là nhiễu từ Client (do cache Service Worker cũ của trình duyệt tại cổng 8000 hoặc Extension).\n"
                    "Dự án này hoàn toàn KHÔNG sử dụng Firebase hay Push Notification.\n"
                    "TUYỆT ĐỐI KHÔNG TẠO tệp `firebase-messaging-sw.js` vào dự án! Đây là request vô hại và không ảnh hưởng đến ứng dụng.\n"
                    "Hãy giải thích cho người dùng biết đây là cache trình duyệt (nhấn F12 > Application > Service workers > Unregister)."
                )

        # 2. Phát hiện lỗi vỡ bảng mã tiếng Việt (dấu ? trong đường dẫn ảnh)
        if re.search(r'/uploads/[^\s\r\n]*\?[^\s\r\n]*', text) or re.search(r'\[404\]:.*?GET\s+/uploads/[^\s\r\n]*\?', text):
            notes.append(
                "⚠️ [CHẨN ĐOÁN CHUYÊN GIA VỀ LỖI ẢNH CHỨA DẤU '?']:\n"
                "Phát hiện đường dẫn tệp ảnh chứa ký tự '?' (ví dụ B?_b?t_t?t.jpg). Đây là dấu hiệu kinh điển của việc vỡ bảng mã UTF-8 từ database MySQL do kết nối chưa thiết lập charset utf8mb4.\n"
                "File ảnh trên ổ đĩa thực tế có dấu tiếng Việt đầy đủ (ví dụ: Bò_bít_tết.jpg).\n"
                "TUYỆT ĐỐI KHÔNG đổi tên file hay sửa đường dẫn gọi ảnh!\n"
                "BẮT BUỘC: Hãy phẫu thuật file kết nối CSDL (như shop/ketnoi.php hoặc config.php) để bổ sung: `mysqli_set_charset($conn, 'utf8mb4');`. Điều này sẽ khắc phục đồng loạt toàn bộ ảnh và dữ liệu tiếng Việt trong dự án!"
            )

        # 3. Phát hiện Fatal error: Call to undefined function
        m_func = re.search(r'Call to undefined function\s+([a-zA-Z0-9_]+)\(\)', text)
        if m_func:
            func_name = m_func.group(1)
            notes.append(
                f"⚠️ [CHẨN ĐOÁN CHUYÊN GIA VỀ LỖI FATAL `{func_name}()`]:\n"
                f"Lỗi Fatal error này làm PHP dừng render HTML đột ngột, khiến các thẻ đóng container/footer bị mất và làm vỡ layout CSS giao diện.\n"
                f"BẮT BUỘC: Cấy ghép hàm `{func_name}()` vào bên trong khối `<?php ... ?>` ở đầu tệp đang gọi nó, HOẶC bổ sung vào file dùng chung như `shop/ketnoi.php` để toàn bộ các trang khác cũng sử dụng được.\n"
                f"ĐỒNG THỜI: Luôn xuất lệnh khởi chạy lại máy chủ (RUN_COMMAND) để kiểm tra giao diện sau khi sửa!"
            )

        if not notes:
            return ""

        return "=== BỘ QUY TẮC CHẨN ĐOÁN KỸ SƯ CHUYÊN SÂU (EXPERT DIAGNOSTIC INSIGHTS) ===\n" + "\n\n".join(notes) + "\n\n"

    def plan_and_graft(self, task: str, target_file: str = None, images: Optional[List[str]] = None) -> Dict[str, Any]:
        prompt = build_graft_prompt(task, self.graph, target_file, project_dir=str(self.root_dir))
        snippets = self.extract_context_snippets_from_text(task)
        expert_notes = self.generate_expert_diagnostic_notes(task)
        if expert_notes or snippets:
            prompt = expert_notes + snippets + prompt
        sys_instruction = get_system_instruction(str(self.root_dir))
        ai_res = self.client.query_ai(prompt, system_prompt=sys_instruction, images=images)

        if not ai_res.get("success"):
            return {
                "success": False,
                "error": ai_res.get("error"),
                "tokens": ai_res.get("tokens", {})
            }

        response_text = ai_res.get("response", "")
        all_actions = self.parse_all_actions(response_text)
        clean_text = self.clean_ai_response(response_text)
        if not clean_text:
            clean_text = response_text

        # Xử lý các Graft Actions
        graft_results = []
        for act in all_actions["graft"]:
            fpath = self.root_dir / act["file"]
            if not fpath.exists():
                graft_results.append({"file": act["file"], "success": False, "error": f"Không tìm thấy file: {act['file']}"})
                continue

            orig_code = fpath.read_text(encoding="utf-8-sig", errors="replace")
            new_code = orig_code
            msg = ""
            action_type = act["action"]

            if action_type == "ENSURE_IMPORT" and act.get("import"):
                new_code = Grafter.ensure_import(orig_code, act["import"])
                msg = f"Đã thêm import: {act['import']}"
                succ = True
            elif action_type == "REPLACE" and act.get("symbol"):
                succ, new_code, msg = Grafter.graft_replace_symbol(
                    orig_code, act["symbol"], act["code"], parent_class=act.get("parent"), file_path=act["file"]
                )
            elif action_type == "INSERT":
                succ, new_code, msg = Grafter.graft_insert_symbol(
                    orig_code, act["code"], parent_class=act.get("parent"), file_path=act["file"]
                )
            else:
                succ = False
                msg = f"Hành động graft không rõ: {action_type}"

            if not succ:
                graft_results.append({"file": act["file"], "success": False, "error": msg})
                continue

            diff = generate_unified_diff(orig_code, new_code, act["file"])
            stats = count_diff_stats(diff)
            graft_results.append({
                "file": act["file"],
                "success": True,
                "msg": msg,
                "diff": diff,
                "stats": stats,
                "original_code": orig_code,
                "new_code": new_code,
                "action": act
            })

        return {
            "success": True,
            "response": clean_text,
            "raw_response": response_text,
            "actions": graft_results,
            "create_files": all_actions["create"],
            "delete_files": all_actions["delete"],
            "commands": all_actions["command"],
            "tokens": ai_res.get("tokens", {})
        }

    def analyze_log_and_plan_next(self, goal: str, last_cmd: str, exit_code: int, log_text: str) -> Dict[str, Any]:
        tail_log = log_text[-4000:] if len(log_text) > 4000 else log_text

        # 1. Chẩn đoán môi trường & thư mục dự án
        doctor_section = ""
        try:
            from .environment_inspector import EnvironmentInspector
            inspection = EnvironmentInspector.inspect_project(str(self.root_dir))
            doctor_section = EnvironmentInspector.format_markdown_report(inspection) + "\n\n"
        except Exception:
            pass

        # 2. Đảm bảo có danh sách tệp tin đã quét trong CodebaseGraph
        if not self.graph.files:
            try:
                self.graph.scan()
            except Exception:
                pass

        file_section = ""
        if self.graph and self.graph.files:
            file_paths = list(self.graph.files.keys())[:80]
            file_section = "=== DANH SÁCH TỆP TIN ĐÃ QUÉT TRONG DỰ ÁN (CODEBASE FILES) ===\n"
            file_section += "(HỆ THỐNG ĐÃ CÓ SẴN CÂY TỆP NÀY. BẠN TUYỆT ĐỐI KHÔNG ĐƯỢC CHẠY LỆNH dir /B, ls, type, cat ĐỂ THĂM DÒ DỰ ÁN!)\n"
            for fp in file_paths:
                file_section += f"- `{fp}`\n"
            if len(self.graph.files) > 80:
                file_section += f"... và {len(self.graph.files) - 80} tệp khác.\n"
            file_section += "\n"

        snippets = self.extract_context_snippets_from_text(log_text)
        expert_notes = self.generate_expert_diagnostic_notes(log_text + "\n" + goal)
        prompt = f"""{expert_notes}{doctor_section}{file_section}{snippets}=== MỤC TIÊU CỦA NGƯỜI DÙNG ===
{goal}

=== TIẾN TRÌNH VỪA CHẠY XONG ===
Lệnh: `{last_cmd}`
Mã thoát (Exit Code): {exit_code} (0 = thành công, khác 0 = lỗi)

=== LOG ĐẦU RA TỪ TERMINAL (REAL-TIME LOG) ===
```
{tail_log}
```

=== NHIỆM VỤ CỦA BẠN ===
Bạn là kỹ sư phần mềm tự động điều phối dự án. Hãy đọc log trên và:
1. Đánh giá kết quả: Lệnh đã chạy thành công hay thất bại? Nguyên nhân cụ thể nếu có lỗi?
2. TỰ ĐỘNG THỰC HIỆN BƯỚC TIẾP THEO:
   - ĐẶC BIỆT LƯU Ý VỀ CÁC TIẾN TRÌNH KHỞI CHẠY ỨNG DỤNG (GUI Desktop App hoặc Script chính):
     Nếu lệnh vừa kết thúc là khởi chạy ứng dụng (ví dụ: `python main.py`, `.venv\\Scripts\\python.exe main.py`, `python run.py`, `npm start`) và Mã thoát: 0 (Thành công) ĐỒNG THỜI KHÔNG CÓ LỖI TRACEBACK:
     Điều này có nghĩa là ứng dụng đã chạy bình thường và người dùng đã đóng cửa sổ GUI (hoặc ứng dụng đã hoàn tất phiên làm việc).
     TUYỆT ĐỐI KHÔNG xuất lệnh mở lại ứng dụng lần nữa!
     TUYỆT ĐỐI KHÔNG chạy các lệnh kiểm tra như `dir /B`, `Get-Content`, `type`!
     BẮT BUỘC: Kết luận ứng dụng đã hoàn tất phiên làm việc thành công và KHÔNG xuất thêm bất kỳ lệnh <<<RUN_COMMAND nào.
   - NẾU GẶP LỖI 404 CỦA PHP BUILT-IN SERVER (`[404]: GET / - No such file or directory`) HOẶC LỖI `Directory ... does not exist`:
     + Nguyên nhân: PHP server đang chạy ở Document Root không có `index.php` hoặc cờ `-t` bị sai đường dẫn so với thư mục làm việc hiện tại (cwd).
     + BẮT BUỘC: Nhìn ngay vào danh sách `CODEBASE FILES` ở trên để tìm xem `index.php` nằm ở đâu (ví dụ: `webquanlynhahang/shop/index.php`).
     + TUYỆT ĐỐI KHÔNG xuất các lệnh terminal dò đường như `dir /B`, `dir /b`, `ls`, `type`, `cat` làm lãng phí các bước tự động!
     + BẮT BUỘC: Xuất ngay lệnh chạy với cờ `-t <đường_dẫn_chứa_index.php>` chính xác tương đối với thư mục làm việc hiện tại, ví dụ:
       `php -S 127.0.0.1:8000 -t webquanlynhahang/shop`
   - NẾU CÓ LỖI KHÁC (Mã thoát khác 0 HOẶC log có Traceback / Exception / Error):
     BẮT BUỘC: Phân tích chính xác nguyên nhân lỗi và TỰ ĐỘNG KHẮC PHỤC:
     + Nếu lỗi thiếu thư viện / runtime (ví dụ ModuleNotFoundError, missing dependency): Hãy xuất khối `<<<RUN_COMMAND` để cài đặt (ví dụ `pip install ...`, `composer require ...`).
     + Nếu lỗi cú pháp hoặc logic mã nguồn (SyntaxError, NameError, TypeError,...): Hãy xuất khối `<<<GRAFT_ACTION` để phẫu thuật sửa file.
       ĐỒNG THỜI: Hãy xuất luôn khối `<<<RUN_COMMAND` để khởi chạy lại ứng dụng/máy chủ nhằm kiểm tra ngay sau khi sửa!
   - NẾU GẶP LỖI CƠ SỞ DỮ LIỆU HOẶC HEALTH PROBE BÁO LỖI (404, 500, `[HEALTH_PROBE_ERROR]`):
     + BẮT BUỘC: Phân tích lỗi cụ thể:
       * Nếu lỗi 404: Xuất lại lệnh chạy với cờ `-t <thư_mục_chứa_index.php>` chính xác.
        * Nếu lỗi database (Unknown database, Table doesn't exist, mysqli_sql_exception):
          Hãy ưu tiên dùng câu lệnh khởi tạo CSDL đã có trong mục "BÁO CÁO CHẨN ĐOÁN (ACTION PLAN)" ở trên hoặc lệnh PowerShell import an toàn. TUYỆT ĐỐI KHÔNG dùng php -r "..." nhiều dòng và TUYỆT ĐỐI KHÔNG sinh file tạm khuôn mẫu vào dự án!
       * Nếu lỗi code PHP / Python: Xuất `<<<GRAFT_ACTION` để phẫu thuật sửa file, VÀ xuất luôn `<<<RUN_COMMAND` để khởi động lại máy chủ!
   - NẾU GẶP LỖI `Call to undefined function <tên_hàm>()`:
     + Đây là nguyên nhân khiến trang web bị dừng render giữa chừng và vỡ giao diện HTML/CSS!
     + BẮT BUỘC: Cấy ghép hàm bổ sung bằng `<<<GRAFT_ACTION Action: INSERT` vào file đang gọi hàm (hệ thống sẽ tự động đưa vào khối <?php đầu tệp) HOẶC bổ sung vào tệp include chung như `shop/ketnoi.php` để toàn bộ các trang khác cũng sử dụng được!
     + ĐỒNG THỜI BẮT BUỘC: Xuất luôn khối `<<<RUN_COMMAND` khởi chạy lại máy chủ (ví dụ: `php -S 127.0.0.1:8000 -t webquanlynhahang/shop`) để hệ thống kiểm tra trang web tự động!
   - NẾU LỆNH VỪA RỒI LÀ CHUẨN BỊ / CÀI ĐẶT / THIẾT LẬP CSDL VÀ THÀNH CÔNG:
     + Xuất ngay `<<<RUN_COMMAND` cho bước tiếp theo để khởi chạy ứng dụng / máy chủ.
   - Nếu mục tiêu của người dùng đã hoàn thành hoặc server đang chạy ổn định: Hãy tóm tắt ngắn gọn và khẳng định ĐÃ HOÀN TẤT (không xuất thêm lệnh).
"""
        sys_instruction = get_system_instruction(str(self.root_dir))
        ai_res = self.client.query_ai(prompt, system_prompt=sys_instruction)
        if not ai_res.get("success"):
            return {
                "success": False,
                "error": ai_res.get("error"),
                "tokens": ai_res.get("tokens", {})
            }

        response_text = ai_res.get("response", "")
        all_actions = self.parse_all_actions(response_text)
        clean_text = self.clean_ai_response(response_text)

        graft_results = []
        for act in all_actions["graft"]:
            fpath = self.root_dir / act["file"]
            if not fpath.exists():
                continue
            orig_code = fpath.read_text(encoding="utf-8-sig", errors="replace")
            new_code = orig_code
            action_type = act["action"]
            if action_type == "ENSURE_IMPORT" and act.get("import"):
                new_code = Grafter.ensure_import(orig_code, act["import"])
                succ = True
                msg = f"Đã thêm import: {act['import']}"
            elif action_type == "REPLACE" and act.get("symbol"):
                succ, new_code, msg = Grafter.graft_replace_symbol(
                    orig_code, act["symbol"], act["code"], parent_class=act.get("parent"), file_path=act["file"]
                )
            elif action_type == "INSERT":
                succ, new_code, msg = Grafter.graft_insert_symbol(
                    orig_code, act["code"], parent_class=act.get("parent"), file_path=act["file"]
                )
            else:
                succ = False
                msg = "Lỗi hành động"
            if succ:
                diff = generate_unified_diff(orig_code, new_code, act["file"])
                graft_results.append({
                    "file": act["file"],
                    "success": True,
                    "msg": msg,
                    "diff": diff,
                    "original_code": orig_code,
                    "new_code": new_code,
                    "action": act
                })

        return {
            "success": True,
            "response": clean_text or response_text,
            "raw_response": response_text,
            "actions": graft_results,
            "create_files": all_actions["create"],
            "delete_files": all_actions["delete"],
            "commands": all_actions["command"],
            "tokens": ai_res.get("tokens", {})
        }

    def create_new_file(self, rel_path: str, code: str) -> Tuple[bool, str]:
        fpath = self.root_dir / rel_path
        try:
            fpath.parent.mkdir(parents=True, exist_ok=True)
            if fpath.exists():
                orig_code = fpath.read_text(encoding="utf-8-sig", errors="replace")
                self.history_backups.append({
                    "type": "modify",
                    "file": str(rel_path),
                    "previous_content": orig_code
                })
            else:
                self.history_backups.append({
                    "type": "create",
                    "file": str(rel_path)
                })
            fpath.write_text(code, encoding="utf-8")
            self.scan()
            return True, f"Đã tạo file thành công: {rel_path}"
        except Exception as e:
            return False, f"Lỗi tạo file {rel_path}: {str(e)}"

    def delete_project_file(self, rel_path: str) -> Tuple[bool, str]:
        fpath = self.root_dir / rel_path
        if not fpath.exists():
            return False, f"File không tồn tại: {rel_path}"
        try:
            orig_code = fpath.read_text(encoding="utf-8-sig", errors="replace")
            self.history_backups.append({
                "type": "delete",
                "file": str(rel_path),
                "previous_content": orig_code
            })
            fpath.unlink()
            self.scan()
            return True, f"Đã xóa file an toàn: {rel_path}"
        except Exception as e:
            return False, f"Lỗi xóa file {rel_path}: {str(e)}"

    def apply_action(self, action_result: Dict[str, Any]) -> Tuple[bool, str]:
        fpath = self.root_dir / action_result["file"]
        try:
            self.history_backups.append({
                "type": "modify",
                "file": action_result["file"],
                "previous_content": action_result["original_code"]
            })
            fpath.write_text(action_result["new_code"], encoding="utf-8")
            self.scan()
            return True, f"Đã lưu cấy ghép vào: {action_result['file']}"
        except Exception as e:
            return False, f"Lỗi lưu file: {str(e)}"

    def undo_last(self) -> Tuple[bool, str]:
        if not self.history_backups:
            return False, "Không có lịch sử để hoàn tác"

        backup = self.history_backups.pop()
        b_type = backup.get("type", "modify")
        fpath = self.root_dir / backup["file"]

        try:
            if b_type == "create":
                if fpath.exists():
                    fpath.unlink()
                self.scan()
                return True, f"Đã xóa file vừa tạo: {backup['file']}"
            elif b_type in ("modify", "delete"):
                fpath.parent.mkdir(parents=True, exist_ok=True)
                fpath.write_text(backup["previous_content"], encoding="utf-8")
                self.scan()
                return True, f"Đã phục hồi trạng thái cũ của: {backup['file']}"
            return False, "Loại sao lưu không hợp lệ"
        except Exception as e:
            return False, f"Lỗi phục hồi: {str(e)}"

    def doctor(self) -> Dict[str, Any]:
        from .environment_inspector import EnvironmentInspector
        inspection = EnvironmentInspector.inspect_project(str(self.root_dir))
        inspection["markdown_report"] = EnvironmentInspector.format_markdown_report(inspection)
        return inspection

