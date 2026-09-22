"""Recognize clear requests to do work, solely for checking response completeness.

This is deliberately conservative and never grants permission to execute an action.
The existing approval/auto-apply settings still control execution.
"""

import re
import unicodedata


def is_action_request(task: str) -> bool:
    text = unicodedata.normalize("NFKD", task.casefold().replace("đ", "d"))
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = " ".join(text.split()).strip()

    # Explicit explanation-only constraints win over an apparent imperative.
    if re.search(
        r"\b(?:chi (?:can )?(?:giai thich|huong dan|cho vi du)|"
        r"(?:only|just) (?:explain|describe|show (?:me )?(?:an? )?example)|"
        r"(?:do not|don't|khong|dung) (?:change|modify|edit|execute|run|sua|chay|tao)\b)",
        text,
    ):
        return False

    vietnamese = (
        r"^(?:(?:hay|vui long|lam on|giup (?:toi|minh)|"
        r"(?:toi|minh) (?:muon|can)|(?:ban )?co the)\s+)*"
        r"(?:ve|tao|sua|fix|chay|cai(?: dat)?|xay dung|trien khai|"
        r"them|cap nhat|chinh sua|xoa|mo|hien thi|viet|lam)\b"
    )
    english = (
        r"^(?:(?:please|help me|(?:can|could|would) you|"
        r"i (?:want|need)(?: you)? to)\s+)*"
        r"(?:create|build|implement|fix|repair|run|start|install|add|update|"
        r"edit|modify|remove|delete|open|display|write|draw|plot|generate|make)\b"
    )
    return bool(re.search(vietnamese, text) or re.search(english, text))
