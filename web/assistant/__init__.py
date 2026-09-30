"""The AI assistant: a question in, an answer worked out by RetPlan's own engine.

:class:`Assistant.ask` runs the tool-use loop. The model sees a redacted brief of
the plan and the enabled tools (web/assistant/tools.py); whenever it asks for a
tool, RetPlan checks the arguments, runs it, redacts the result and hands it
back - at most ``assistant.max_tool_calls`` times. The final text has its names
restored and is shown with the disclaimer and the list of tool calls that
produced its figures. A tool that writes (a new scenario) is not run: it becomes
a proposal the person approves or declines (:meth:`Assistant.confirm`).

Provider and model are abstractions (web/assistant/providers.py), chosen by
``assistant.provider`` / ``assistant.model`` or on the Assistant settings page.
Every setting is read live (web/assistant/settings.py). The design is
docs/07-ai-assistant.md.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import json
import logging
import threading
import time
import uuid

from web.assistant import providers
from web.assistant.privacy import Redactor
from web.assistant.prompts import system_prompt
from web.assistant.settings import AssistantSettings
from web.assistant.store import ConversationStore
from web.assistant.tools import BY_NAME, ToolContext, enabled_tools, validate

logger = logging.getLogger(__name__)
RESULT_LIMIT = 24_000          # characters of one tool result sent back to the model
HISTORY = 20                   # earlier messages of a conversation sent with a question
PENDING_TTL = 3600             # seconds a proposed write waits for approval


class AssistantUnavailable(Exception):
    """The assistant cannot answer: switched off, not allowed, over a limit, no provider."""


def plan_brief(plan) -> str:
    people = ", ".join(f"{p.label} {p.age:g} (retires at {p.retire_age:g})" for p in plan.persons)
    savings = sum(lg.opening for lg in plan.ledgers if lg.enabled and plan.wrappers[lg.wrapper].liquid)
    p0 = plan.persons[0]
    spend = sum(e.amount for e in plan.expenses if e.enabled and not (e.recur_years and e.recur_years > 1)
                and e.start_age <= p0.age <= e.end_age)
    return (f"Plan: {plan.label}. People: {people}. Savings about {savings:,.0f}; spending about "
            f"{spend:,.0f} a year now; {len(plan.income)} income streams, {len(plan.ledgers)} "
            f"accounts, {len(plan.loans)} loans. Confidence target {plan.policy.confidence:.0%}. "
            + ("Accounts come from a linked portfolio." if plan.portfolio_id else ""))


def _summary(result) -> str:
    text = json.dumps(result, default=str)
    return text if len(text) <= 400 else text[:397] + "…"


class Assistant:
    def __init__(self, app, provider: providers.LLMProvider | None = None):
        self.app = app
        self.provider_override = provider
        self.pending: dict[str, dict] = {}
        self._lock = threading.Lock()

    @property
    def store(self) -> ConversationStore:
        return ConversationStore(self.app.state.db)

    def settings(self) -> AssistantSettings:
        return AssistantSettings.load(self.app.state.config, self.app.state.db)

    def provider(self, s: AssistantSettings):
        return self.provider_override or s.provider_obj()

    def check(self, is_admin: bool, s: AssistantSettings | None = None) -> tuple[bool, str]:
        """(may this person ask now, why not)."""
        s = s or self.settings()
        if not s.enabled:
            return False, "The assistant is switched off."
        if s.access == "admin" and not is_admin:
            return False, "The assistant is available to the administrator only."
        if self.provider_override is None:
            ok, why = s.status()
            if not ok:
                return False, why
        return True, ""

    # -- one question ------------------------------------------------------------
    def ask(self, sid: str, question: str, cid: int | None = None, mode: str = "chat",
            is_admin: bool = False) -> dict:
        s = self.settings()
        ok, why = self.check(is_admin, s)
        if not ok:
            raise AssistantUnavailable(why)
        question = (question or "").strip()[:4000]
        if not question:
            raise AssistantUnavailable("Ask a question first.")
        store = self.store
        if s.questions_per_hour and store.questions_last_hour(sid) >= s.questions_per_hour:
            raise AssistantUnavailable(f"The limit of {s.questions_per_hour} questions an hour is "
                                       "reached; try again later.")
        if s.daily_token_budget and store.tokens_today() >= s.daily_token_budget:
            raise AssistantUnavailable("Today's budget for the assistant is used up; it resets "
                                       "tomorrow.")
        store.prune(s.retention_days)

        plan = self.app.state.store.get(sid)
        red = Redactor(s.share_names, s.round_money_to).learn_plan(plan)
        for i, pf in enumerate(self.app.state.portfolios.list(sid)):
            red.learn(pf["name"], f"Portfolio {i + 1}")
        ctx = ToolContext(self.app, sid, s, red, plan)

        conversation = store.get(sid, cid) if cid else None
        history = []
        if conversation:
            for m in store.messages(sid, conversation["id"])[-HISTORY:]:
                history.append({"role": m["role"], "text": red.text(m["content"])})
        provider = self.provider(s)
        model_id = s.strategy_model if mode in ("strategy", "report") else s.model
        model = provider.model(model_id)
        tools = enabled_tools(s) if model.tools else []
        system = system_prompt(s, red.text(plan_brief(plan)))
        messages = history + [{"role": "user", "text": red.text(question)}]
        calls, pending, tokens_in, tokens_out = [], [], 0, 0
        answer, error = "", None
        try:
            for step in range(s.max_tool_calls + 1):
                reply = provider.reply(model_id, system, messages, [t.spec() for t in tools], s)
                tokens_in += reply.tokens_in
                tokens_out += reply.tokens_out
                if not reply.tool_calls:
                    answer = reply.text
                    break
                if step == s.max_tool_calls:
                    answer = (reply.text or "") + ("\n\n(I stopped here: this question reached the "
                                                   f"limit of {s.max_tool_calls} calls to RetPlan.)")
                    break
                messages.append({"role": "assistant", "text": reply.text,
                                 "tool_calls": reply.tool_calls})
                results = []
                for call in reply.tool_calls:
                    content, is_error, entry = self._run_tool(ctx, s, call, tools, sid, cid, pending)
                    calls.append(entry)
                    results.append(providers.ToolResult(call.id, content, is_error))
                messages.append({"role": "user", "tool_results": results})
        except providers.ProviderError as exc:
            logger.warning("assistant provider failed: %s", exc)
            error = str(exc)
            answer = "The assistant could not reach its model just now. " + str(exc)
        answer = red.restore(answer or "(no answer)")
        tokens = tokens_in + tokens_out
        store.count(sid, tokens)
        if s.keep_conversations:
            if conversation is None:
                cid = store.create(sid, question[:80])
            store.add(cid, "user", question)
            store.add(cid, "assistant", answer, calls if s.log_tool_calls else [],
                      tokens_in, tokens_out, model_id)
            for p in pending:
                p["cid"] = cid
        else:
            cid = None
        return dict(answer=answer, conversation=cid, tool_calls=calls if s.log_tool_calls else [],
                    pending=[dict(id=p["id"], text=p["text"]) for p in pending],
                    provider=provider.key, model=model_id, tokens=tokens, error=error,
                    disclaimer=s.disclaimer)

    def _run_tool(self, ctx, s, call, tools, sid, cid, pending):
        red = ctx.redactor
        tool = BY_NAME.get(call.name)
        entry = dict(name=call.name, input=call.input)
        if tool is None or tool not in tools:
            entry["summary"] = "not available"
            return json.dumps({"error": f"The tool '{call.name}' is not available."}), True, entry
        problem = validate(tool, call.input or {})
        if problem:
            entry["summary"] = f"refused: {problem}"
            return json.dumps({"error": problem}), True, entry
        args = json.loads(red.restore(json.dumps(call.input or {})))   # names back for RetPlan
        if tool.writes and s.confirm_writes:
            pid = uuid.uuid4().hex[:12]
            text = red.restore(tool.describe(args)) if tool.describe else f"Run {tool.name}."
            with self._lock:
                self._expire()
                self.pending[pid] = dict(id=pid, owner=sid, tool=tool.name, args=args, text=text,
                                         created=time.time(), cid=cid)
            pending.append(self.pending[pid])
            entry["summary"] = "proposed - waiting for approval"
            return json.dumps({"status": "awaiting_approval", "proposal": red.text(text),
                               "note": "Tell the person what you propose; they approve or "
                                       "decline it below your answer."}), False, entry
        try:
            result = tool.handler(ctx, args)
        except Exception as exc:  # noqa: BLE001 - reported to the model, logged here
            logger.exception("assistant tool %s failed", tool.name)
            entry["summary"] = f"failed: {exc}"
            return json.dumps({"error": f"{tool.name} failed: {exc}"}), True, entry
        safe = red.data(result)
        entry["summary"] = red.restore(_summary(safe))
        return json.dumps(safe, default=str)[:RESULT_LIMIT], "error" in (result or {}), entry

    # -- approving a proposed write -------------------------------------------------
    def _expire(self):
        now = time.time()
        for k in [k for k, v in self.pending.items() if now - v["created"] > PENDING_TTL]:
            self.pending.pop(k, None)

    def confirm(self, sid: str, pid: str, approve: bool, is_admin: bool = False) -> dict:
        s = self.settings()
        ok, why = self.check(is_admin, s)
        if not ok:
            raise AssistantUnavailable(why)
        with self._lock:
            self._expire()
            p = self.pending.get(pid)
            if p is None or p["owner"] != sid:
                raise AssistantUnavailable("That proposal has expired - ask again.")
            self.pending.pop(pid, None)
        if not approve:
            message = "Declined - nothing was changed."
        else:
            tool = BY_NAME[p["tool"]]
            if not tool.enabled(s):
                raise AssistantUnavailable("That action is no longer allowed.")
            plan = self.app.state.store.get(sid)
            ctx = ToolContext(self.app, sid, s, Redactor(True), plan)
            result = tool.handler(ctx, p["args"])
            message = result.get("error") or f"Done: {result.get('saved', '')}. {result.get('note', '')}"
        if s.keep_conversations and p.get("cid") and self.store.get(sid, p["cid"]):
            self.store.add(p["cid"], "assistant", message)
        return dict(message=message.strip(), approved=approve)
