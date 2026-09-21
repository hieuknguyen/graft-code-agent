"""Application configuration and safe credential handling.

Gemini credentials are deliberately environment-only. A project config file is
easy to commit or share by accident, so it must never be used as a source for a
direct Gemini API key.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


CONFIG_FILE = Path(__file__).parent / "config.yaml"

GEMINI_PROVIDER = "gemini"
GATEWAY_PROVIDER = "gateway"
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"


def _normalise_provider(value: object) -> str:
    """Return a supported provider, defaulting to direct Gemini safely."""
    provider = str(value or "").strip().lower()
    aliases = {
        "direct": GEMINI_PROVIDER,
        "google": GEMINI_PROVIDER,
        "google-genai": GEMINI_PROVIDER,
        "legacy": GATEWAY_PROVIDER,
        "legacy_gateway": GATEWAY_PROVIDER,
    }
    provider = aliases.get(provider, provider)
    return provider if provider in {GEMINI_PROVIDER, GATEWAY_PROVIDER} else GEMINI_PROVIDER


def _as_bool(value: Any, default: bool) -> bool:
    """Avoid treating strings such as ``\"false\"`` as truthy configuration."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off", ""}:
            return False
    return default


@dataclass
class AppConfig:
    # ``gemini`` calls the Google Gen AI SDK directly. ``gateway`` preserves
    # compatibility with the project's previous HTTP gateway integration.
    provider: str = GEMINI_PROVIDER
    gateway_url: str = "http://localhost:5678/webhook/antigravity-chat"
    api_key: str = ""  # Legacy gateway key only; never used for direct Gemini.
    model: str = DEFAULT_GEMINI_MODEL
    evaluator_model: str = "claude-sonnet-4-6"
    dual_ai_mode: bool = False
    # File writes and command execution must require approval by default.
    auto_apply: bool = False
    thinking: bool = True
    web_search: bool = True
    # 0 = Không giới hạn số lệnh (Unlimited command executions)
    max_feedback_loops: int = 0
    # Kept out of repr so diagnostics and UI cannot accidentally disclose it.
    # It is populated only from GEMINI_API_KEY, never config.yaml.
    gemini_api_key: str = field(default="", repr=False)

    @property
    def uses_direct_gemini(self) -> bool:
        return self.provider == GEMINI_PROVIDER


def _read_yaml() -> dict[str, Any]:
    if not CONFIG_FILE.exists():
        return {}

    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as config_file:
            data = yaml.safe_load(config_file) or {}
        if not isinstance(data, dict):
            print("[Cảnh báo] config.yaml phải là một mapping YAML; bỏ qua nội dung không hợp lệ.")
            return {}
        return data
    except Exception as exc:
        print(f"[Cảnh báo] Lỗi đọc config.yaml: {exc}")
        return {}


def load_config() -> AppConfig:
    """Load non-secret settings, then apply environment-based credentials.

    ``GEMINI_API_KEY`` and ``GEMINI_MODEL`` are the direct Gemini settings.
    ``GRAFT_*`` settings remain available for the legacy gateway.
    """
    cfg = AppConfig()
    data = _read_yaml()

    # Resolve the provider before loading any credential. An old config file
    # without ``provider`` that contains an API key is treated as a legacy
    # gateway config, preserving existing installs while new configs default to
    # direct Gemini. GEMINI_* environment variables explicitly select Gemini.
    env_provider = os.environ.get("GRAFT_PROVIDER")
    if env_provider:
        cfg.provider = _normalise_provider(env_provider)
    elif "provider" in data:
        cfg.provider = _normalise_provider(data.get("provider"))
    elif data.get("api_key") and not (
        os.environ.get("GEMINI_API_KEY") or os.environ.get("GEMINI_MODEL")
    ):
        cfg.provider = GATEWAY_PROVIDER

    # Credentials are handled below. In particular, do not read a YAML
    # ``api_key`` at all while using direct Gemini.
    scalar_fields = ("gateway_url", "model", "evaluator_model")
    bool_fields = ("dual_ai_mode", "auto_apply", "thinking", "web_search")
    for name in scalar_fields:
        value = data.get(name)
        if isinstance(value, str) and value.strip():
            setattr(cfg, name, value.strip())
    for name in bool_fields:
        if name in data:
            setattr(cfg, name, _as_bool(data[name], getattr(cfg, name)))

    if "max_feedback_loops" in data:
        try:
            cfg.max_feedback_loops = max(0, int(data["max_feedback_loops"]))
        except (ValueError, TypeError):
            cfg.max_feedback_loops = 0

    # Generic environment variables preserve old gateway deployments.
    cfg.gateway_url = os.environ.get("GRAFT_GATEWAY_URL", cfg.gateway_url).strip()
    cfg.model = os.environ.get("GRAFT_MODEL", cfg.model).strip()

    if cfg.provider == GEMINI_PROVIDER:
        # Direct Gemini is intentionally env-only; never fall back to YAML or
        # GRAFT_API_KEY, even if an old config file happens to contain a key.
        cfg.gemini_api_key = os.environ.get("GEMINI_API_KEY", "").strip()
        cfg.model = os.environ.get("GEMINI_MODEL", cfg.model).strip()
        cfg.api_key = ""
    else:
        yaml_gateway_key = data.get("api_key", "")
        if isinstance(yaml_gateway_key, str):
            cfg.api_key = yaml_gateway_key.strip()
        cfg.api_key = os.environ.get("GRAFT_API_KEY", cfg.api_key).strip()

    return cfg


def save_config(cfg: AppConfig) -> None:
    """Persist non-secret settings.

    The direct Gemini API key is intentionally excluded. A legacy gateway key
    is saved only when the user explicitly selects the legacy gateway provider.
    """
    provider = _normalise_provider(cfg.provider)
    cfg.provider = provider
    data: dict[str, Any] = {
        "provider": provider,
        "gateway_url": cfg.gateway_url,
        "model": cfg.model,
        "evaluator_model": cfg.evaluator_model,
        "dual_ai_mode": cfg.dual_ai_mode,
        "auto_apply": cfg.auto_apply,
        "thinking": cfg.thinking,
        "web_search": cfg.web_search,
        "max_feedback_loops": getattr(cfg, "max_feedback_loops", 0),
    }
    if provider == GATEWAY_PROVIDER and cfg.api_key:
        data["api_key"] = cfg.api_key

    with open(CONFIG_FILE, "w", encoding="utf-8") as config_file:
        yaml.safe_dump(data, config_file, default_flow_style=False, allow_unicode=True, sort_keys=False)
