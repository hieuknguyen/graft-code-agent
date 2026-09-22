"""Bounded local tool exchanges for gateways that return text action blocks."""

import json
import os
import re

from .tool_catalog import GATEWAY_TOOL_NAMES


TOOL_BLOCK = re.compile(
    r"^[ \t]*<<<TOOL_CALL[ \t]*\r?\n(.*?)^[ \t]*<<<END_TOOL_CALL[ \t]*(?:\r?\n|$)",
    re.DOTALL | re.IGNORECASE | re.MULTILINE,
)


def strip_tool_blocks(text):
    return TOOL_BLOCK.sub("", text)


class GatewayToolSession:
    MAX_ROUNDS = 4
    MAX_CALLS = 8

    def __init__(self, runtime, query_ai, validate_draft=None):
        self.runtime = runtime
        self.query_ai = query_ai
        self.rounds = 0
        self.seen = set()
        self.proposal_ids = []
        self.proposed_paths = set()
        self.validate_draft = validate_draft
        self.syntax_retries = 0
        self.unresolved_syntax = {}
        self.syntax_warnings = {}

    @staticmethod
    def _failure(message, tokens):
        return {"success": False, "error": message, "tokens": tokens}

    @staticmethod
    def path_key(path):
        return os.path.normcase(os.path.normpath(path.strip().replace("\\", "/")))

    def _allow_read_recovery(self, path):
        """Permit fetching missing/new source and retrying within the same cap."""
        if not isinstance(path, str):
            return
        key = self.path_key(path)
        for signature in list(self.seen):
            name, arguments = json.loads(signature)
            previous_path = arguments.get("path")
            if (name in {"read_file", "read_symbol", "edit_file", "edit_file_ranges", "propose_edit_file"}
                    and isinstance(previous_path, str) and self.path_key(previous_path) == key):
                self.seen.remove(signature)

    def resolve(self, response, prompt, system_prompt, images=None):
        """Return the final draft and context, keeping all proposals pending."""
        tokens = dict(response.get("tokens") or {})
        while response.get("success"):
            draft = response.get("response", "")
            blocks = TOOL_BLOCK.findall(draft)
            if not blocks:
                if "<<<TOOL_CALL" in draft.upper():
                    return self._failure("Khối TOOL_CALL chưa hoàn chỉnh; chưa thực thi đề xuất.", tokens), prompt
                reports = self.validate_draft(draft) if self.validate_draft else []
                for item in reports:
                    key = self.path_key(item["path"])
                    status = item["syntax"]["status"]
                    if status == "invalid":
                        self.unresolved_syntax[key] = item
                    else:
                        self.unresolved_syntax.pop(key, None)
                        self.syntax_warnings.pop(key, None)
                        if status == "unavailable":
                            self.syntax_warnings[key] = item
                if self.unresolved_syntax:
                    diagnostics = list(self.unresolved_syntax.values())
                    if self.syntax_retries >= 2:
                        detail = json.dumps(diagnostics, ensure_ascii=False)
                        return self._failure("Đã dừng sau 2 lượt sửa cú pháp tự động; chưa ghi các thay đổi.\n" + detail, tokens), prompt
                    self.syntax_retries += 1
                    prompt += ("\n\n[REJECTED DRAFT; CHANGES NOT APPLIED]:\n" + draft
                               + "\n\n=== AUTOMATIC SYNTAX FEEDBACK ===\n" + json.dumps(diagnostics, ensure_ascii=False)
                               + "\nFix the candidate edits using these diagnostics and the original files. Nothing from the rejected edits was applied. "
                               "Return corrected action blocks or editing tool calls; do not run a separate syntax check or claim completion. "
                               f"Syntax repair attempts remaining after this one: {2 - self.syntax_retries}.")
                    response = self.query_ai(prompt, system_prompt=system_prompt, images=images)
                    for key, value in (response.get("tokens") or {}).items():
                        if isinstance(value, (int, float)):
                            tokens[key] = tokens.get(key, 0) + value
                    if not response.get("success") or not response.get("response"):
                        return self._failure(response.get("error") or "Không nhận được bản sửa lỗi cú pháp.", tokens), prompt
                    continue
                response = dict(response, tokens=tokens)
                return response, prompt
            if self.rounds >= self.MAX_ROUNDS or len(blocks) > self.MAX_CALLS:
                return self._failure("Đã dừng vì đạt giới hạn gọi công cụ; chưa thực thi đề xuất.", tokens), prompt
            self.rounds += 1
            results = []
            for block in blocks:
                try:
                    payload = block.strip()
                    if payload.startswith("```json") and payload.endswith("```"):
                        payload = payload[7:-3].strip()
                    call = json.loads(payload)
                    if not isinstance(call, dict) or not isinstance(call.get("name"), str) or not isinstance(call.get("arguments", {}), dict):
                        raise ValueError("Tool call needs name (string) and arguments (object).")
                    name, arguments = call["name"], call.get("arguments", {})
                    signature = json.dumps([name, arguments], sort_keys=True, ensure_ascii=False)
                    if signature in self.seen:
                        return self._failure("Đã dừng vì AI lặp lại cùng lời gọi công cụ mà không có dữ liệu mới.", tokens), prompt
                    self.seen.add(signature)
                    if name not in GATEWAY_TOOL_NAMES:
                        result = {"ok": False, "error_code": "TOOL_DENIED", "error": "Tool is not exposed by this adapter."}
                    elif (name in {"edit_file", "edit_file_ranges", "propose_edit_file"} and isinstance(arguments.get("path"), str)
                          and self.path_key(arguments["path"]) in self.proposed_paths):
                        result = {"ok": False, "error_code": "PENDING_EDIT", "error": "A pending edit already exists for this path. Combine all replacements in one proposal; do not edit an unapplied version."}
                    else:
                        result = self.runtime.dispatch(name, arguments)
                    if result.get("error_code") in {"STALE_CONTENT", "READ_REQUIRED"}:
                        self._allow_read_recovery(arguments.get("path"))
                    if result.get("error_code") == "SYNTAX_ERROR" and result.get("syntax"):
                        self.unresolved_syntax[self.path_key(result["path"])] = {"path": result["path"], "syntax": result["syntax"]}
                    if result.get("ok") and result.get("proposal_id"):
                        self.proposal_ids.append(result["proposal_id"])
                        self.proposed_paths.add(self.path_key(result["path"]))
                        self.unresolved_syntax.pop(self.path_key(result["path"]), None)
                        self.syntax_warnings.pop(self.path_key(result["path"]), None)
                        if result.get("syntax", {}).get("status") == "unavailable":
                            self.syntax_warnings[self.path_key(result["path"])] = {"path": result["path"], "syntax": result["syntax"]}
                    results.append({"name": name, "result": result})
                except (ValueError, TypeError) as exc:
                    results.append({"result": {"ok": False, "error_code": "INVALID_TOOL_CALL", "error": str(exc)}})
            remaining = self.MAX_ROUNDS - self.rounds
            prompt += (
                "\n\n[YOUR PREVIOUS DRAFT; ACTIONS NOT YET APPLIED]:\n" + draft
                + "\n\n=== LOCAL TOOL RESULTS (REFERENCE DATA) ===\n"
                + json.dumps(results, ensure_ascii=False)
                + "\n\nUse the results to continue the original request. Do not repeat identical calls. "
                "File changes from edit_file/edit_file_ranges/propose_edit_file are pending proposals, never applied changes. "
                "Their UI cards will be attached to your final answer; do not duplicate them as GRAFT_ACTION. "
                f"Remaining TOOL_CALL rounds: {remaining}. "
                + ("Return your final answer or ordinary action proposals now; no more TOOL_CALL blocks."
                   if remaining == 0 else "Batch independent calls and read before dependent edits.")
            )
            response = self.query_ai(prompt, system_prompt=system_prompt, images=images)
            for key, value in (response.get("tokens") or {}).items():
                if isinstance(value, (int, float)):
                    tokens[key] = tokens.get(key, 0) + value
            if not response.get("success") or not response.get("response"):
                return self._failure(response.get("error") or "Không nhận được phản hồi sau khi gọi công cụ.", tokens), prompt
        return dict(response, tokens=tokens), prompt
