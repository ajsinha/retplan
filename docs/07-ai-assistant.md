# 07 · AI assistant — design

Status: **designed, configuration in place, not yet built.** The `assistant:` section of
`config/retplan.yaml` already exists (off by default) so the design below is anchored to real
settings. Nothing in RetPlan calls a language model today.

## 1. What it is for, and the rules it keeps

An optional assistant, powered by Claude, that people can talk to about their plan:

| Feature | Config key | What it does |
|---|---|---|
| Intake | `assistant.features.intake` | "Tell me about your situation" becomes a filled-in plan; every value is confirmed before anything is saved. |
| Explain the strategy | `assistant.features.explain_strategy` | Explains the strategy optimiser's result: why claim at 70, what each change is worth, what would change the answer. |
| What-if | `assistant.features.what_if` | "What if I work part-time to 65?" — the assistant changes a copy of the plan, runs it, and answers with the odds. |
| Review | `assistant.features.review` | Points out risks and gaps: no health cover before Medicare, forced withdrawals pushing up a bracket, a survivor's income drop, spending below essentials. |
| Report | `assistant.features.report` | Writes the strategy report in readable prose. |

Five rules, enforced in code rather than by the prompt:

1. **The engine produces every number.** The model can only obtain figures by calling RetPlan's
   tools; the system prompt forbids arithmetic of its own, and every figure in an answer is
   traceable to a logged tool call.
2. **Off unless configured.** `assistant.enabled: false` and no API key means no code path can
   contact a model. The UI shows nothing.
3. **Everything is a setting.** Provider, key, models, who may use it, which features and tools,
   what data leaves the machine, limits, logging and prompts — all under `assistant.*`, read
   live (the configurator re-reads the files every `app.reload_seconds`), so switching it off
   takes effect without a restart.
4. **Private by default.** Names become "Person 1", "Account 2"; money is rounded; holdings are
   not sent unless allowed; the person can see exactly what will be sent.
5. **Writes are rare and confirmed.** By default the assistant can only *add a scenario*, never
   change the active plan, and asks first.

## 2. Architecture

```
web/assistant/
  __init__.py       Assistant: one question in, an answer out (the tool-use loop)
  settings.py       AssistantSettings.from_config(cfg) - every assistant.* key, read live
  provider.py       Provider protocol; AnthropicProvider (Messages API with tools);
                    FakeProvider (scripted, for tests); NoProvider
  tools.py          the tool registry: name, description, JSON schema, handler,
                    writes?, the config key that enables it
  context.py        the plan and portfolios as the model sees them - redacted and rounded
  privacy.py        Redactor: names -> placeholders (and back, for display), rounding
  prompts.py        the built-in system prompt; assistant.prompts.system_file replaces it
  store.py          conversations, messages, tool calls, token usage (database)
  limits.py         questions per hour per workspace; the daily token budget
routes/assistant_routes.py
  GET  /assistant                    the chat page (and a panel on dashboard / plan / strategy)
  POST /api/assistant/ask            one question -> streamed answer + the tool calls made
  POST /api/assistant/confirm/{id}   approve or decline a pending write
  GET  /api/assistant/preview        exactly what would be sent about this plan
  POST /assistant/{cid}/delete       forget a conversation
```

**The loop.** `Assistant.ask(question)` sends the system prompt, the redacted plan summary and the
conversation to the provider with the enabled tools; while the model asks for tools (at most
`assistant.max_tool_calls`), each call is validated against its schema, run by RetPlan, logged,
and its result returned; the final text is un-redacted for display ("Person 1" → "Maria") and
shown with the disclaimer and a "how this was worked out" list of the tool calls.

**Provider.** `assistant.provider: anthropic` uses the official `anthropic` Python SDK
(a new dependency, installed only when wanted) with `assistant.model` for conversation and
`assistant.strategy_model` for explanations and reports; `assistant.base_url` allows a
gateway. The `Provider` protocol keeps the door open for another vendor or a local model later
without touching tools or routes.

## 3. Tools

Each tool is enabled by `assistant.tools.<name>`; disabled tools are never offered to the model.

| Tool | Setting | Writes | Calls |
|---|---|---|---|
| `get_plan_summary` | `read_plan` | no | ages, income, spending, accounts, loans, policy, assumptions (redacted) |
| `get_results` | `read_plan` | no | the last simulation's odds, wealth bands, depletion age |
| `get_portfolios` | `read_portfolios` | no | net worth, accounts by kind, allocation (holdings only if `privacy.share_holdings`) |
| `run_simulation` | `run_simulation` | no | the plan, or a copy with adjustments (`levers.Adjust`: retire, spend, save, equity, fee, claim) |
| `find_levers` | `run_simulation` | no | `levers.levers` - the biggest single changes |
| `explore_claiming` | `run_simulation` | no | `levers.claiming` |
| `explore_conversions` | `run_simulation` | no | `levers.conversions` |
| `spending_check` | `run_simulation` | no | `levers.spending_check` |
| `draw_orders` | `run_simulation` | no | `levers.draw_orders` |
| `run_strategy` / `strategy_result` | `run_optimiser` | no | `web.strategy` - starts a search, then reads its result |
| `search_help` | always | no | the help centre and glossary, to explain terms |
| `save_scenario` | `save_scenario` | **yes** | a new scenario from adjustments or a strategy - the active plan is untouched |
| `edit_plan` | `edit_plan` (off) | **yes** | changes one item of the active plan, through the same validation as the dialogs |

With `assistant.tools.confirm_writes: true` a write is not executed: the answer shows a
"Save this scenario? / No thanks" card and the write runs only on approval.

## 4. Privacy

`web/assistant/privacy.py` builds the model's view of the plan:

- **Names** (`privacy.share_names: false`): people become "Person 1/2", accounts
  "Account n (Roth IRA)", institutions are dropped, the plan and scenario names become "Your
  plan". The map lives only in the request and is used to restore names in the answer.
- **Money** is rounded to `privacy.round_money_to` (1,000 by default) before it is sent.
- **Holdings** (`privacy.share_holdings: false`): only the allocation by asset class and tax
  treatment is sent, not symbols or quantities.
- **Preview**: `/api/assistant/preview` shows the exact payload, from a "What is sent?" link.
- **Nothing else**: no email, workspace id, IP address or session data is ever included.

## 5. Safety

- **Disclaimer** (`assistant.prompts.disclaimer`) on every answer; the prompt frames answers as
  education from the model's own figures, and declines to pick individual securities or give
  legal or tax-filing advice.
- **Prompt injection**: plan labels, notes and spreadsheet contents are data - passed inside
  tool results, never concatenated into instructions; tool arguments are schema-validated and
  bounded (ages, percentages, amounts).
- **Bounded cost**: `max_tool_calls`, `max_tokens`, `timeout_seconds`; `limits.questions_per_hour`
  per workspace and `limits.daily_token_budget` across all, enforced before each call; usage is
  recorded per request.
- **Access**: `assistant.access: admin` limits it to the administrator (e.g. while trying it out).
- **Failure**: a provider error or a budget stop answers plainly ("The assistant is unavailable
  right now") and never breaks the page.

## 6. Data

Three new tables, in both schema files (no migrations — added the usual way):

| Table | Holds |
|---|---|
| `assistant_conversations` | `id`, `owner`, `title`, `created_at`, `updated_at` |
| `assistant_messages` | `conversation_id`, `role`, `content` (as displayed), `tool_calls` (JSON: name, arguments, result summary), `tokens_in`, `tokens_out`, `model`, `created_at` |
| `assistant_usage` | `day`, `owner`, `questions`, `tokens` - for the limits |

`assistant.logging.keep_conversations: false` keeps nothing but usage counts;
`retention_days` prunes older conversations daily; a person can delete a conversation at any time.

## 7. Configuration

All under `assistant:` in `config/retplan.yaml` (see the configuration guide for each key):
`enabled`, `provider`, `api_key` (from `ANTHROPIC_API_KEY` or `config/retplan.local.yaml`,
never the committed file), `base_url`, `model`, `strategy_model`, `max_tokens`, `temperature`,
`timeout_seconds`, `max_tool_calls`, `access`, `features.*`, `tools.*`, `privacy.*`, `limits.*`,
`logging.*`, `prompts.*`. The System page shows the effective settings (never the key).

## 8. Testing

- A `FakeProvider` scripted with tool requests and final text, so every test runs offline.
- Tool contract tests: each tool's schema, bounds and result shape; disabled tools are not offered.
- Privacy tests: with `share_names: false`, no person, account or institution name appears in
  any payload; amounts are rounded; holdings are absent unless allowed.
- Limits and budget tests; confirmation flow tests (no write without approval).
- Configuration tests: flipping `assistant.enabled` in the local overlay takes effect after a
  reload, without a restart.

## 9. Build order

1. **Read-only Q&A and what-if** - settings, provider, tools (read and simulate), privacy,
   limits, the chat panel. Useful on its own and writes nothing.
2. **Strategy explanation and report** - `run_strategy` / `strategy_result`, the strategy model,
   a "Explain this strategy" button on the strategy page, a printable report.
3. **Intake and scenarios** - `save_scenario` with confirmation; conversational set-up.
4. **Review** - deterministic checks first (no health cover before 65, required withdrawals, a
   survivor's drop), the model explaining and prioritising them.
5. **Other providers or a local model** behind the same `Provider` protocol, if wanted.

## 10. Decisions to make before building

- Which models by default (Sonnet 5.5 for conversation and Opus 5.5 for strategy are the
  configured defaults).
- Whether everyone may use it or only the administrator at first (`assistant.access`).
- Whether it may ever change the active plan (`tools.edit_plan`), or only add scenarios.
- How long conversations are kept (`logging.retention_days`).
