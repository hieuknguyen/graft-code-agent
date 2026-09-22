"""Gemini function-calling orchestration for the local coding agent.

The Gemini API decides *which* tool it needs.  :mod:`core.tool_runtime`
decides what that tool is allowed to do.  In particular, write/delete/command
calls create proposals only; a model response can never apply them.
"""

from __future__ import annotations

import base64
import binascii
import json
import os
from typing import Any, Dict, Iterable, List, Optional

from .tool_runtime import ToolRuntime
from .tool_catalog import CODING_TOOL_SCHEMAS


from .prompts import GEMINI_SYSTEM_INSTRUCTION as SYSTEM_INSTRUCTION


class GeminiCodingAgent:
    """Manual Gemini function-call loop compatible with the official google-genai SDK."""

    _EDIT_TOOL_NAMES = frozenset({"edit_file", "edit_file_ranges", "propose_edit_file", "propose_write_file"})

    def __init__(self, config: Any, runtime: ToolRuntime):
        self.config = config
        self.runtime = runtime

    @staticmethod
    def _tool_schemas() -> List[Dict[str, Any]]:
        return list(CODING_TOOL_SCHEMAS) + [
            {
                "name": "project_overview",
                "description": "Get a safe high-level manifest of the imported project before investigating it.",
                "parameters_json_schema": {"type": "object", "properties": {}},
            },
            {
                "name": "list_files",
                "description": "List non-sensitive project files below a relative directory. This never reads file contents.",
                "parameters_json_schema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Relative project directory, or empty for root."},
                        "depth": {"type": "integer", "description": "Directory depth from 0 to 8."},
                        "max_results": {"type": "integer", "description": "Maximum rows, at most 500."},
                    },
                },
            },
            {
                "name": "search_project",
                "description": "Search literal text in safe text files. Use this to locate implementations before reading them.",
                "parameters_json_schema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Literal text to find."},
                        "glob": {"type": "string", "description": "Optional glob such as **/*.py."},
                        "max_results": {"type": "integer", "description": "Maximum matches, at most 80."},
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "read_file",
                "description": "Read a safe UTF-8 project file with line numbers and a version hash. Use the hash when proposing an edit.",
                "parameters_json_schema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Relative project file path."},
                        "start_line": {"type": "integer", "description": "One-based first line; defaults to 1."},
                        "end_line": {"type": "integer", "description": "One-based last line; capped for context safety."},
                    },
                    "required": ["path"],
                },
            },
            {
                "name": "propose_write_file",
                "description": "Prepare a complete-file create or modification for explicit user approval. This does not write to disk.",
                "parameters_json_schema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Relative target file path."},
                        "content": {"type": "string", "description": "Complete new UTF-8 content."},
                        "expected_sha256": {"type": "string", "description": "sha256 returned by read_file for existing files."},
                        "description": {"type": "string", "description": "Short explanation for the approval card."},
                    },
                    "required": ["path", "content"],
                },
            },
            {
                "name": "propose_delete_file",
                "description": "Prepare a text-file deletion for explicit user approval. This never deletes immediately.",
                "parameters_json_schema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Relative project file path."},
                        "description": {"type": "string", "description": "Reason for deletion."},
                    },
                    "required": ["path"],
                },
            },
            {
                "name": "propose_run_command",
                "description": "Prepare a normal command with a program and separate arguments. It waits for explicit user approval.",
                "parameters_json_schema": {
                    "type": "object",
                    "properties": {
                        "program": {"type": "string", "description": "Executable, for example python, npm, git."},
                        "args": {"type": "array", "items": {"type": "string"}, "description": "Individual command arguments."},
                        "cwd": {"type": "string", "description": "Relative working directory, empty means project root."},
                        "timeout_seconds": {"type": "integer", "description": "Requested timeout; max 1800."},
                        "description": {"type": "string", "description": "What the command will verify or do."},
                    },
                    "required": ["program"],
                },
            },
            {
                "name": "propose_powershell",
                "description": "Prepare a PowerShell script only when cmd/program+args cannot express the task. Always high-risk and needs approval.",
                "parameters_json_schema": {
                    "type": "object",
                    "properties": {
                        "script": {"type": "string", "description": "PowerShell script without encoded commands, bypass, elevation, or recursive delete."},
                        "cwd": {"type": "string", "description": "Relative project working directory."},
                        "timeout_seconds": {"type": "integer", "description": "Requested timeout; max 1800."},
                        "description": {"type": "string", "description": "Why PowerShell is needed."},
                    },
                    "required": ["script"],
                },
            },
        ]

    @staticmethod
    def _path_key(path: Any) -> Optional[str]:
        if not isinstance(path, str):
            return None
        return os.path.normcase(os.path.normpath(path.strip().replace("\\", "/")))

    @staticmethod
    def _usage(response: Any) -> Dict[str, int]:
        usage = getattr(response, "usage_metadata", None)
        if not usage:
            return {}
        return {
            "input_tokens": int(getattr(usage, "prompt_token_count", 0) or 0),
            "output_tokens": int(getattr(usage, "candidates_token_count", 0) or 0),
            "total_tokens": int(getattr(usage, "total_token_count", 0) or 0),
        }

    @staticmethod
    def _data_uri_parts(types: Any, images: Iterable[str]) -> List[Any]:
        parts: List[Any] = []
        for image in images or []:
            if not isinstance(image, str) or not image.startswith("data:"):
                continue
            try:
                header, payload = image.split(",", 1)
                if ";base64" not in header:
                    continue
                mime_type = header[5:].split(";", 1)[0]
                raw = base64.b64decode(payload, validate=True)
                if not mime_type.startswith("image/") or not raw or len(raw) > 5 * 1024 * 1024:
                    continue
                parts.append(types.Part.from_bytes(data=raw, mime_type=mime_type))
            except (ValueError, binascii.Error):
                continue
        return parts

    @staticmethod
    def _response_text(response: Any) -> str:
        try:
            text = response.text
            if text:
                return str(text)
        except Exception:
            pass
        return ""

    def run(self, task: str, target_file: Optional[str] = None, images: Optional[List[str]] = None) -> Dict[str, Any]:
        """Run at most ``gemini_max_tool_rounds`` Gemini/tool exchanges."""
        try:
            from google import genai
            from google.genai import types
        except ImportError:
            return {
                "success": False,
                "error": "Thiếu package google-genai. Hãy chạy: pip install -r requirements.txt",
            }

        api_key = getattr(self.config, "gemini_api_key", "") or os.environ.get("GEMINI_API_KEY", "")
        if not api_key:
            return {
                "success": False,
                "error": "Chưa có GEMINI_API_KEY. Hãy đặt biến môi trường này trước khi chạy ứng dụng.",
            }

        try:
            client = genai.Client(api_key=api_key)
            declarations = [
                types.FunctionDeclaration(
                    name=item["name"],
                    description=item["description"],
                    parameters_json_schema=item["parameters_json_schema"],
                )
                for item in self._tool_schemas()
            ]
            tool = types.Tool(function_declarations=declarations)
            config = types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                tools=[tool],
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            )

            prompt = task.strip() or "Analyze the attached images and answer in the user's language, defaulting to Vietnamese."
            if target_file:
                prompt += f"\n\nUser-selected priority file: `{target_file}`. Read it with the available tools before drawing conclusions."
            user_parts = [types.Part.from_text(text=prompt)] + self._data_uri_parts(types, images or [])
            contents: List[Any] = [types.Content(role="user", parts=user_parts)]
            proposal_ids: List[str] = []
            proposed_paths = set()
            unresolved_syntax: Dict[str, Dict[str, Any]] = {}
            syntax_warnings: Dict[str, Dict[str, Any]] = {}
            syntax_retries = 0
            token_totals = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
            max_rounds = max(1, min(int(getattr(self.config, "gemini_max_tool_rounds", 12)), 24))

            for _round in range(max_rounds):
                response = client.models.generate_content(
                    model=getattr(self.config, "model", None) or os.environ.get("GEMINI_MODEL", "gemini-3.8-flash"),
                    contents=contents,
                    config=config,
                )
                usage = self._usage(response)
                for key, value in usage.items():
                    token_totals[key] = token_totals.get(key, 0) + value

                calls = list(getattr(response, "function_calls", None) or [])
                if not calls:
                    if unresolved_syntax:
                        diagnostics = json.dumps(list(unresolved_syntax.values()), ensure_ascii=False)
                        if syntax_retries >= 2:
                            return {
                                "success": False,
                                "error": "Đã dừng sau 2 lượt sửa cú pháp tự động; chưa áp dụng đề xuất hoặc chạy lệnh.\n" + diagnostics,
                                "tokens": token_totals,
                            }
                        syntax_retries += 1
                        contents.append(types.Content(role="model", parts=[types.Part.from_text(
                            text=self._response_text(response) or "No corrected file proposal was returned.",
                        )]))
                        contents.append(types.Content(role="user", parts=[types.Part.from_text(text=(
                            "=== AUTOMATIC SYNTAX FEEDBACK ===\n" + diagnostics
                            + "\nThe candidate edits above were rejected and the original files are unchanged. "
                            "Use editing tools to return corrected proposals based on these diagnostics and the original files. "
                            "Do not run a separate syntax check, claim completion or run dependent commands. "
                            f"Syntax repair attempts remaining after this one: {2 - syntax_retries}."
                        ))]))
                        continue
                    return {
                        "success": True,
                        "response": self._response_text(response) or "Gemini đã hoàn tất phân tích.",
                        "proposal_ids": proposal_ids,
                        "syntax_warnings": list(syntax_warnings.values()),
                        "tokens": token_totals,
                    }

                candidate = None
                try:
                    candidate = response.candidates[0].content
                except (AttributeError, IndexError, TypeError):
                    return {"success": False, "error": "Gemini trả về function call không có nội dung hội thoại hợp lệ."}
                contents.append(candidate)
                function_response_parts: List[Any] = []
                for call in calls:
                    name = getattr(call, "name", "")
                    args = dict(getattr(call, "args", None) or {})
                    if name in self._EDIT_TOOL_NAMES and self._path_key(args.get("path")) in proposed_paths:
                        tool_result = {
                            "ok": False, "error_code": "PENDING_EDIT",
                            "error": "A pending edit already exists for this path. Combine all replacements in one proposal; do not edit an unapplied version.",
                        }
                    else:
                        tool_result = self.runtime.dispatch(name, args)
                    path = tool_result.get("path")
                    path_key = self._path_key(path)
                    if path_key is not None and tool_result.get("error_code") == "SYNTAX_ERROR" and tool_result.get("syntax"):
                        unresolved_syntax[path_key] = {"path": path, "syntax": tool_result["syntax"]}
                    if tool_result.get("ok") and tool_result.get("proposal_id"):
                        proposal_ids.append(str(tool_result["proposal_id"]))
                        if path_key is not None:
                            if name in self._EDIT_TOOL_NAMES:
                                proposed_paths.add(path_key)
                            unresolved_syntax.pop(path_key, None)
                            syntax_warnings.pop(path_key, None)
                            if tool_result.get("syntax", {}).get("status") == "unavailable":
                                syntax_warnings[path_key] = {"path": path, "syntax": tool_result["syntax"]}
                    kwargs: Dict[str, Any] = {"name": name, "response": tool_result}
                    call_id = getattr(call, "id", None)
                    if call_id:
                        kwargs["id"] = call_id
                    function_response_parts.append(types.Part.from_function_response(**kwargs))
                # Gemini expects function responses as the next user turn; the original
                # model function-call content above is preserved verbatim in history.
                contents.append(types.Content(role="user", parts=function_response_parts))

            if unresolved_syntax:
                return {
                    "success": False,
                    "error": f"Dừng agent sau {max_rounds} lượt vì lỗi cú pháp chưa được sửa; chưa áp dụng đề xuất hoặc chạy lệnh.\n"
                             + json.dumps(list(unresolved_syntax.values()), ensure_ascii=False),
                    "tokens": token_totals,
                }
            return {
                "success": False,
                "error": f"Dừng agent sau {max_rounds} lượt tool-call để tránh vòng lặp vô hạn.",
                "proposal_ids": proposal_ids,
                "tokens": token_totals,
            }
        except Exception as exc:
            return {"success": False, "error": f"Gemini API lỗi: {exc}"}
