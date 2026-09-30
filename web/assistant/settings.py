"""The assistant's settings: ``assistant.*`` in config/retplan.yaml, read live.

Every key is read from the configuration each time the assistant is used, so a
change to the YAML (or to config/retplan.local.yaml) takes effect at the next
reload, without a restart.

The provider and the two models can also be switched by the administrator on
the Assistant settings page. Those choices are kept in the database
(``app_settings``: ``assistant.ui.provider``, ``assistant.ui.model``,
``assistant.ui.strategy_model``) and win over the configuration until they are
reset; the page says which is in force and where it came from.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

from dataclasses import dataclass, field

UI_KEYS = ("provider", "model", "strategy_model")
FEATURES = ("intake", "explain_strategy", "what_if", "review", "report")
TOOL_SWITCHES = ("read_plan", "read_portfolios", "run_simulation", "run_optimiser",
                 "save_scenario", "edit_plan")


@dataclass
class AssistantSettings:
    enabled: bool = False
    provider: str = "anthropic"
    api_key: str = ""
    base_url: str = ""
    model: str = "claude-sonnet-5-5"
    strategy_model: str = "claude-opus-5-5"
    max_tokens: int = 4000
    temperature: float = 0.2
    timeout_seconds: float = 60
    max_tool_calls: int = 12
    access: str = "everyone"
    features: dict = field(default_factory=lambda: {f: True for f in FEATURES})
    tools: dict = field(default_factory=lambda: {t: t != "edit_plan" for t in TOOL_SWITCHES})
    confirm_writes: bool = True
    share_names: bool = False
    share_holdings: bool = False
    round_money_to: float = 1000
    questions_per_hour: int = 30
    daily_token_budget: int = 2_000_000
    keep_conversations: bool = True
    retention_days: int = 30
    log_tool_calls: bool = True
    system_file: str = ""
    disclaimer: str = ("Educational, not financial advice. Every figure comes from RetPlan's "
                       "model and is only as good as its assumptions.")
    sources: dict = field(default_factory=dict)     # provider/model/strategy_model -> config|ui

    @classmethod
    def load(cls, cfg, db=None) -> "AssistantSettings":
        s = cls()
        if cfg is None:
            return s
        g = cfg.get
        s.enabled = cfg.get_bool("assistant.enabled", s.enabled)
        s.provider = str(g("assistant.provider", s.provider) or s.provider).strip()
        s.api_key = str(g("assistant.api_key", "") or "").strip()
        s.base_url = str(g("assistant.base_url", "") or "").strip()
        s.model = str(g("assistant.model", s.model) or s.model).strip()
        s.strategy_model = str(g("assistant.strategy_model", s.strategy_model) or s.model).strip()
        s.max_tokens = max(256, cfg.get_int("assistant.max_tokens", s.max_tokens))
        s.temperature = cfg.get_float("assistant.temperature", s.temperature)
        s.timeout_seconds = max(5.0, cfg.get_float("assistant.timeout_seconds", s.timeout_seconds))
        s.max_tool_calls = max(0, cfg.get_int("assistant.max_tool_calls", s.max_tool_calls))
        s.access = str(g("assistant.access", s.access) or "everyone").strip().lower()
        s.features = {f: cfg.get_bool(f"assistant.features.{f}", True) for f in FEATURES}
        s.tools = {t: cfg.get_bool(f"assistant.tools.{t}", t != "edit_plan") for t in TOOL_SWITCHES}
        s.confirm_writes = cfg.get_bool("assistant.tools.confirm_writes", True)
        s.share_names = cfg.get_bool("assistant.privacy.share_names", False)
        s.share_holdings = cfg.get_bool("assistant.privacy.share_holdings", False)
        s.round_money_to = max(0.0, cfg.get_float("assistant.privacy.round_money_to", 1000))
        s.questions_per_hour = max(0, cfg.get_int("assistant.limits.questions_per_hour", 30))
        s.daily_token_budget = max(0, cfg.get_int("assistant.limits.daily_token_budget", 2_000_000))
        s.keep_conversations = cfg.get_bool("assistant.logging.keep_conversations", True)
        s.retention_days = max(1, cfg.get_int("assistant.logging.retention_days", 30))
        s.log_tool_calls = cfg.get_bool("assistant.logging.log_tool_calls", True)
        s.system_file = str(g("assistant.prompts.system_file", "") or "").strip()
        s.disclaimer = str(g("assistant.prompts.disclaimer", s.disclaimer) or s.disclaimer)
        s.sources = {k: "config" for k in UI_KEYS}
        if db is not None:
            for k in UI_KEYS:
                v = db.get_setting(f"assistant.ui.{k}")
                if v:
                    setattr(s, k, str(v))
                    s.sources[k] = "ui"
        return s

    def provider_obj(self):
        from web.assistant import providers
        return providers.get(self.provider)

    def status(self) -> tuple[bool, str]:
        """(ready, why not) - whether a question could be answered now."""
        if not self.enabled:
            return False, "The assistant is switched off (assistant.enabled)."
        if self.provider in ("", "none"):
            return False, "No provider is chosen (assistant.provider is none)."
        p = self.provider_obj()
        if p is None:
            return False, f"Unknown provider '{self.provider}'."
        return p.available(self)

    def public(self) -> dict:
        """What the System and settings pages may show - never the key."""
        return dict(enabled=self.enabled, provider=self.provider, model=self.model,
                    strategy_model=self.strategy_model, access=self.access,
                    key_set=bool(self.api_key), base_url=self.base_url or "(default)",
                    features=self.features, tools=self.tools, sources=self.sources)


def save_ui_choice(db, key: str, value: str | None) -> None:
    """Keep (or with None, forget) the administrator's choice of provider or model."""
    if key not in UI_KEYS:
        raise ValueError(key)
    db.set_setting(f"assistant.ui.{key}", value or "")
