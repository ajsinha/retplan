"""The assistant's tools: the only way it can learn a number.

Each tool is a thin wrapper over something RetPlan already computes - the plan,
the last simulation, a what-if, the claiming and conversion explorers, the
spending check, the draw order, the strategy optimiser, the portfolios, the
help centre. A tool has a name, a description and a JSON Schema for its input
(what the model sees), a handler (what RetPlan runs), whether it writes, and the
configuration switches that must be on for it to be offered at all.

Writes are few: saving a scenario and creating a plan from a conversation. Both
add a new scenario and leave the active plan untouched; with
``assistant.tools.confirm_writes`` they wait for the person's approval. Changing
the active plan (``assistant.tools.edit_plan``) is not offered in this version.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import copy
import math
import time
from dataclasses import dataclass, field
from typing import Callable

from web import levers, strategy, wizard
from web.assistant.review import review as review_plan


@dataclass
class ToolContext:
    """What a handler can reach: the app's state, the workspace, the settings and
    the request's redactor."""
    app: object
    sid: str
    settings: object
    redactor: object
    _plan: object = None

    @property
    def store(self):
        return self.app.state.store

    def plan(self):
        if self._plan is None:
            self._plan = self.store.get(self.sid)
        return self._plan


@dataclass
class Tool:
    name: str
    description: str
    schema: dict
    handler: Callable
    switches: tuple = ()                 # assistant.tools.* that must be on
    features: tuple = ()                 # assistant.features.* - at least one must be on
    writes: bool = False
    describe: Callable | None = None     # a write's one-line summary, for the approval card

    def enabled(self, s) -> bool:
        if not all(s.tools.get(k, False) for k in self.switches):
            return False
        return not self.features or any(s.features.get(f, False) for f in self.features)

    def spec(self) -> dict:
        return {"name": self.name, "description": self.description, "schema": self.schema}


def _obj(props: dict | None = None, required=()) -> dict:
    return {"type": "object", "properties": props or {}, "required": list(required),
            "additionalProperties": False}


def _life(x):
    return None if x is None or x >= 150 else round(x, 1)


# --------------------------------------------------------------------------- #
# reading
# --------------------------------------------------------------------------- #
def get_plan_summary(ctx, args):
    p = ctx.plan()
    names = [x.label for x in p.persons]

    def who(i):
        return names[i] if 0 <= i < len(names) else "Household"
    eq = strategy._equity_share(p)
    return dict(
        plan=p.label, people=[dict(name=x.label, age=x.age, retires_at=x.retire_age,
                                   plans_to_age=x.death_age) for x in p.persons],
        income=[dict(label=r.label, owner=who(r.owner), kind=r.category.replace("_", " "),
                     amount_a_year=r.amount, in_todays_money=r.basis == "real",
                     from_age=r.start_age, to_age=_life(r.end_age),
                     taxable_share=r.taxable_fraction, survivor_share=r.survivor_fraction,
                     included=r.enabled) for r in p.income],
        spending=[dict(label=e.label, amount=e.amount, every_years=e.recur_years or 1,
                       essential=e.essential, from_age=e.start_age, to_age=_life(e.end_age),
                       above_inflation=e.infl_delta, included=e.enabled) for e in p.expenses],
        accounts=[dict(label=lg.label, taxed_as=p.wrappers[lg.wrapper].label,
                       owner=who(lg.owner), balance=lg.opening,
                       saving_a_year=lg.contribution, saving_share_of_pay=lg.contribution_pct_income,
                       employer_match_up_to_share_of_pay=lg.employer_match_cap_pct,
                       draw_order=lg.withdraw_priority, from_linked_portfolio=bool(lg.account_id),
                       included=lg.enabled) for lg in p.ledgers],
        loans=[dict(label=ln.label, balance=ln.balance, rate=ln.rate, years_left=ln.term_years)
               for ln in p.loans if ln.enabled],
        share_in_shares=eq,
        spending_policy=p.policy.method.replace("_", " "),
        confidence_target=p.policy.confidence, leave_at_least=p.policy.legacy_target,
        inflation=p.market.inflation.mean, fees=p.platform_fee + p.adviser_fee,
        tax_bands=[dict(from_income=lo, rate=r) for lo, r in zip(p.tax.ordinary.lowers,
                                                                  p.tax.ordinary.rates)],
        conversions=[dict(label=c.label, mode=c.mode, amount=c.amount, from_age=c.start_age,
                          to_age=c.end_age) for c in p.conversions if c.enabled],
        linked_to_portfolio=bool(p.portfolio_id))


def get_results(ctx, args):
    r = ctx.store.results(ctx.sid)
    if not r:
        return dict(simulated=False,
                    note="No simulation has been run on this plan yet; run_simulation gives the odds.")
    k = r["kpis"]
    out = dict(simulated=True, futures=r["trials"], chance_of_success=k["success_probability"],
               error_bar=1.96 * k["success_se"], median_final_wealth=k["terminal_real_p50"],
               bad_luck_final_wealth=k["terminal_real_p5"],
               money_runs_out_at_age_when_it_fails=None if math.isnan(k["depletion_age_p50"])
               else k["depletion_age_p50"], lifetime_tax_median=k["total_tax_p50"])
    d = (r.get("drawrate") or {}).get("suggested")
    if d:
        out["suggested_first_year_draw_rate"] = d["rate"]
    return out


def get_portfolios(ctx, args):
    repo = ctx.app.state.portfolios
    everything = repo.all_valuation(ctx.sid)
    out = dict(net_worth_all_accounts=everything.net_worth, investable=everything.total,
               property=everything.property_total, debts=everything.debts,
               currency=everything.currency, portfolios=[])
    for i, pf in enumerate(repo.list(ctx.sid)):
        ctx.redactor.learn(pf["name"], f"Portfolio {i + 1}")
        v = repo.valuation(ctx.sid, pf["id"])
        entry = dict(name=pf["name"], net_worth=v.net_worth, investable=v.total,
                     property=v.property_total, debts=v.debts,
                     by_asset_class={k: w for k, _, w in v.by("asset_class")},
                     by_tax_treatment={k: w for k, _, w in v.by_tax()},
                     accounts=[dict(kind=a.kind, type=a.label, owner=a.owner_label, value=a.value)
                               for a in v.accounts])
        if ctx.settings.share_holdings:
            entry["holdings"] = [dict(symbol=p.symbol, quantity=p.quantity, value=p.value,
                                      asset_class=p.asset_class)
                                 for p in v.positions if not p.synthetic]
        out["portfolios"].append(entry)
    return out


def search_help(ctx, args):
    from web.help_catalog import search
    q = str(args.get("query") or "")[:200]
    return dict(topics=[dict(title=t["title"], summary=t["summary"]) for t in search(q)[:6]])


# --------------------------------------------------------------------------- #
# running the model
# --------------------------------------------------------------------------- #
ADJUST = {
    "retire_years": {"type": "number", "minimum": -15, "maximum": 15,
                     "description": "Everyone retires this many years later (+) or earlier (-)."},
    "spend_change": {"type": "number", "minimum": -0.9, "maximum": 2,
                     "description": "Every spending row up or down by this share, e.g. -0.1 for 10% less."},
    "save_more": {"type": "number", "minimum": 0, "maximum": 1e7,
                  "description": "Save this much more a year until retiring (by spending less)."},
    "shares_change": {"type": "number", "minimum": -1, "maximum": 1,
                      "description": "Move this share of every account between bonds and shares, e.g. 0.1."},
    "fee_change": {"type": "number", "minimum": -0.05, "maximum": 0.05,
                   "description": "Change in the yearly platform fee, e.g. -0.0025."},
    "claim_years": {"type": "number", "minimum": -10, "maximum": 10,
                    "description": "Every public pension starts this many years later (+) or earlier (-)."},
}


def _adjust(args):
    return levers.Adjust.from_dict({"retire": args.get("retire_years"),
                                    "spend": args.get("spend_change"),
                                    "save": args.get("save_more"),
                                    "equity": args.get("shares_change"),
                                    "fee": args.get("fee_change"),
                                    "claim": args.get("claim_years")})


def run_simulation(ctx, args):
    plan = ctx.plan()
    base = levers.run(plan)
    adj = _adjust(args)
    out = dict(plan_as_it_is=base, futures=base["trials"])
    if not adj.is_zero():
        out["changed"] = dict(what=adj.describe(), **levers.run(levers.apply(plan, adj)))
        out["change_in_chance_of_success"] = out["changed"]["success"] - base["success"]
    return out


def find_levers(ctx, args):
    r = levers.levers(ctx.plan())
    return dict(base_chance=r["base"]["success"], noise=r["noise"],
                levers=[dict(change=x["label"], change_in_chance=x["delta"],
                             median_wealth_change=x.get("delta_p50")) for x in r["rows"]])


def explore_claiming(ctx, args):
    plan = ctx.plan()
    rows = strategy.pension_rows(plan)
    if not rows:
        return dict(note="No public pension in this plan has a claiming age still to choose.")
    person = args.get("person")
    s = strategy.Settings.from_config(ctx.app.state.config)
    out = []
    for row in rows:
        r = plan.income[row]
        if person is not None and r.owner != int(person):
            continue
        owner = plan.persons[min(r.owner, len(plan.persons) - 1)]
        ages = [a for a in range(int(s.claim_min), int(s.claim_max) + 1) if a >= owner.age]
        res = levers.claiming(plan, row, ages, s.claim_early, s.claim_late)
        out.append(dict(pension=r.label, owner=owner.label, planned_age=r.start_age,
                        best_age=res["best"]["age"],
                        ages=[dict(age=x["age"], amount_a_year=x["amount"], chance=x["success"],
                                   median_final_wealth=x["p50"], breakeven_age=x["breakeven"])
                              for x in res["rows"]]))
    return dict(pensions=out)


def explore_conversions(ctx, args):
    plan = ctx.plan()
    pair = strategy.conversion_setup(plan)
    if not pair:
        return dict(note="Conversions need an account taxed on the way out and one never taxed again.")
    p0 = plan.persons[0]
    start = float(args.get("from_age") or max(math.ceil(p0.age), p0.retire_age))
    end = float(args.get("to_age") or start + 7)
    lowers = sorted(set(plan.tax.ordinary.lowers))
    r = levers.conversions(plan, pair[0], pair[1], start, end, amounts=[10000, 25000, 50000],
                           fill_levels=[lv for lv in lowers[2:5] if lv > 0],
                           heir_rate=strategy.Settings.from_config(ctx.app.state.config).heir_tax_rate)
    return dict(source=plan.ledgers[pair[0]].label, target=plan.ledgers[pair[1]].label,
                from_age=start, to_age=end,
                strategies=[dict(strategy=x["label"], chance=x["success"],
                                 after_tax_left=x["after_tax_p50"], lifetime_tax=x["tax"],
                                 after_tax_gain=x["delta_after_tax"]) for x in r["rows"]],
                best=r["best"]["label"])


def spending_check(ctx, args):
    r = levers.spending_check(ctx.plan(), savings=args.get("savings_today"))
    return dict(verdict=r["verdict"], spending_now=r["now"], chance=r["success"],
                target=r["target"], spending_at_target=r["at_target"], change=r["change"],
                trim_if_chance_below=r["lower"], raise_if_chance_above=r["upper"])


def draw_orders(ctx, args):
    r = levers.draw_orders(ctx.plan())
    if not r.get("rows"):
        return dict(note=r.get("note", "Nothing to order."))
    return dict(orders=[dict(order=x["names"], current=x["current"], chance=x["success"],
                             after_tax_left=x["after_tax_p50"], lifetime_tax=x["tax"])
                        for x in r["rows"]], best=r["best"]["names"])


def review(ctx, args):
    return dict(findings=review_plan(ctx.plan(), ctx.store.results(ctx.sid)))


# --------------------------------------------------------------------------- #
# the strategy optimiser
# --------------------------------------------------------------------------- #
def _strategy_summary(result: dict) -> dict:
    return dict(objective=result["objective"], target=result["target"],
                meets_target=result["meets_target"],
                chance_now=result["baseline"]["success"],
                chance_with_strategy=result["strategy"]["success"],
                after_tax_left_now=result["baseline"]["after_tax"],
                after_tax_left_with_strategy=result["strategy"]["after_tax"],
                decisions=[dict(decision=d["label"], now=d["current"], recommended=d["recommended"],
                                changed=d["changed"],
                                worth_in_chance=(d["worth"] or {}).get("success"),
                                worth_after_tax=(d["worth"] or {}).get("after_tax"))
                           for d in result["decisions"]],
                rules=result["rules"],
                just_as_good=[dict(changes=a["changes"], chance=a["success"])
                              for a in result["alternatives"]],
                key_years=[dict(ages=y["ages"], events=y["events"]) for y in result["timeline"]
                           if y["events"]])


def run_strategy(ctx, args):
    jobs = ctx.app.state.strategy_jobs
    plan = ctx.plan()
    s = strategy.Settings.from_config(ctx.app.state.config)
    target = args.get("target")
    jid = jobs.start(ctx.sid, plan, objective=args.get("objective") or "odds",
                     target=float(target) if target else None, settings=s)
    deadline = time.time() + s.max_seconds + 30
    while time.time() < deadline:
        job = jobs.get(ctx.sid, jid)
        if job["status"] != "running":
            break
        time.sleep(0.5)
    job = jobs.get(ctx.sid, jid)
    if job["status"] != "done":
        return dict(error=job["error"] or "The search did not finish in time.")
    return dict(job=jid, **_strategy_summary(job["result"]))


def strategy_result(ctx, args):
    job = ctx.app.state.strategy_jobs.latest(ctx.sid)
    if not job or job["status"] != "done":
        return dict(note="No strategy has been found for this plan yet; run_strategy finds one.")
    return dict(job=job["id"], **_strategy_summary(job["result"]))


# --------------------------------------------------------------------------- #
# writing: new scenarios only
# --------------------------------------------------------------------------- #
def save_scenario(ctx, args):
    from retplan.plan import plan_from_dict
    name = (str(args.get("name") or "").strip() or "Assistant's scenario")[:80]
    if args.get("from_strategy"):
        job = ctx.app.state.strategy_jobs.latest(ctx.sid)
        if not job or job["status"] != "done":
            return dict(error="There is no finished strategy to save.")
        plan = plan_from_dict(job["result"]["plan"])
    else:
        plan = levers.apply(ctx.plan(), _adjust(args.get("adjustments") or {}))
    ctx.store.create(ctx.sid, name, plan, activate=False)
    return dict(saved=name, note="Saved as a new scenario; the active plan is unchanged.")


def _describe_save(args):
    what = "the strategy" if args.get("from_strategy") else (
        _adjust(args.get("adjustments") or {}).describe())
    return f"Save a new scenario “{args.get('name') or 'Assistant’s scenario'}”: {what}."


INTAKE = {
    "age": {"type": "number", "minimum": 16, "maximum": 100},
    "retire_age": {"type": "number", "minimum": 16, "maximum": 100},
    "plan_to": {"type": "number", "minimum": 50, "maximum": 120,
                "description": "The age to plan to."},
    "partner": {"type": "boolean"},
    "p2_age": {"type": "number"}, "p2_retire_age": {"type": "number"},
    "salary": {"type": "number", "minimum": 0}, "p2_salary": {"type": "number", "minimum": 0},
    "pension": {"type": "number", "minimum": 0, "description": "Public pension a year at pension_age."},
    "pension_age": {"type": "number"}, "p2_pension": {"type": "number", "minimum": 0},
    "k401": {"type": "number", "minimum": 0, "description": "401(k) balance."},
    "k401_save": {"type": "number", "minimum": 0, "maximum": 100, "description": "% of pay saved into it."},
    "k401_match": {"type": "number", "minimum": 0, "maximum": 100, "description": "Employer match up to % of pay."},
    "ira": {"type": "number", "minimum": 0}, "roth_ira": {"type": "number", "minimum": 0},
    "brokerage": {"type": "number", "minimum": 0}, "cash": {"type": "number", "minimum": 0},
    "spend": {"type": "number", "minimum": 0, "description": "What the household spends a year now."},
    "retire_spend_pct": {"type": "number", "minimum": 10, "maximum": 200},
    "essential_pct": {"type": "number", "minimum": 0, "maximum": 100},
    "mortgage": {"type": "number", "minimum": 0}, "mortgage_rate": {"type": "number"},
    "mortgage_years": {"type": "number"},
    "risk": {"type": "string", "enum": ["conservative", "balanced", "growth"]},
    "tax": {"type": "string", "enum": ["us", "flat", "none", "sample"]},
}


def create_plan(ctx, args):
    answers = dict(wizard.DEFAULTS)
    a = dict(args.get("answers") or {})
    for k, v in a.items():
        if k not in INTAKE:
            continue
        answers[k] = ("1" if v else "") if k == "partner" else str(v)
    for key in ("ira", "roth_ira", "brokerage", "cash", "k401"):
        if key in a:
            answers[f"has_{key}"] = "1" if float(a[key] or 0) > 0 else ""
    problems = [e for step, *_ in wizard.STEPS for e in wizard.validate(step, answers)]
    if problems:
        return dict(error="The answers do not make a plan yet: " + " ".join(problems))
    plan = wizard.build_plan(answers)
    name = (str(args.get("name") or "").strip() or "Plan from our conversation")[:80]
    ctx.store.create(ctx.sid, name, plan, activate=False)
    return dict(saved=name, note="Created as a new scenario; open it from Scenarios.")


def _describe_create(args):
    a = args.get("answers") or {}
    return (f"Create a new scenario “{args.get('name') or 'Plan from our conversation'}” "
            f"from your answers (age {a.get('age', '?')}, retiring at {a.get('retire_age', '?')}).")


# --------------------------------------------------------------------------- #
# the registry
# --------------------------------------------------------------------------- #
TOOLS: list[Tool] = [
    Tool("get_plan_summary", "The active plan: people, income, spending, accounts, loans, "
         "policy, assumptions and tax bands. Amounts are a year, in today's money.",
         _obj(), get_plan_summary, ("read_plan",)),
    Tool("get_results", "The last full simulation of the plan: chance of success, final wealth, "
         "tax, the suggested draw rate.", _obj(), get_results, ("read_plan",)),
    Tool("get_portfolios", "Net worth over all accounts and each portfolio's value, allocation "
         "and accounts.", _obj(), get_portfolios, ("read_portfolios",)),
    Tool("search_help", "Search RetPlan's help centre and glossary to explain a term or screen.",
         _obj({"query": {"type": "string", "maxLength": 200}}, ["query"]), search_help),
    Tool("run_simulation", "Simulate the plan as it is, and optionally with changes, on 800 "
         "futures; returns the chance of success, median and bad-luck final wealth, the age the "
         "money runs out when it fails, and lifetime tax.",
         _obj(ADJUST), run_simulation, ("run_simulation",), ("what_if",)),
    Tool("find_levers", "Try each common single change (retire later or earlier, spend less, save "
         "more, shares, fees, claiming) and rank them by what they do to the odds.",
         _obj(), find_levers, ("run_simulation",), ("what_if", "review")),
    Tool("explore_claiming", "For each public pension still to be claimed, the odds, amount and "
         "break-even age at every claiming age.",
         _obj({"person": {"type": "integer", "minimum": 0, "maximum": 3,
                          "description": "Only this person's pensions (0 = the first)."}}),
         explore_claiming, ("run_simulation",), ("what_if", "explain_strategy")),
    Tool("explore_conversions", "Compare no conversion with Roth-style conversions of fixed "
         "amounts and filling the lower tax bands, after the tax heirs would pay.",
         _obj({"from_age": {"type": "number"}, "to_age": {"type": "number"}}),
         explore_conversions, ("run_simulation",), ("what_if", "explain_strategy")),
    Tool("spending_check", "Raise, hold or trim spending this year: the odds across spending "
         "levels and the guardrails around the target.",
         _obj({"savings_today": {"type": "number", "minimum": 0,
                                 "description": "Savings today, if markets have moved."}}),
         spending_check, ("run_simulation",), ("what_if", "review")),
    Tool("draw_orders", "Every order of drawing on the accounts, compared on odds, lifetime tax "
         "and what is left after tax.", _obj(), draw_orders, ("run_simulation",),
         ("what_if", "explain_strategy")),
    Tool("review_plan", "RetPlan's own checks for risks and gaps in the plan (health cover before "
         "65, required withdrawals, a survivor's income, emergency cash, risk near retirement, the "
         "odds against the target).", _obj(), review, ("read_plan",), ("review",)),
    Tool("run_strategy", "Find the strategy - retirement ages, claiming ages, spending policy, "
         "draw order, conversions, share in shares - chosen together for one objective. Takes "
         "about a minute.",
         _obj({"objective": {"type": "string", "enum": ["odds", "earliest", "spend", "legacy"],
                             "description": "odds = safest; earliest = retire earliest; "
                                            "spend = spend the most; legacy = leave the most."},
               "target": {"type": "number", "minimum": 0.5, "maximum": 0.99,
                          "description": "Confidence target as a fraction, e.g. 0.85."}}),
         run_strategy, ("run_optimiser",), ("explain_strategy", "report")),
    Tool("strategy_result", "The latest strategy found for this plan, if any.", _obj(),
         strategy_result, ("run_optimiser",), ("explain_strategy", "report")),
    Tool("save_scenario", "Save a new scenario - the plan with changes, or the latest strategy. "
         "The active plan is never changed. Needs the person's approval.",
         _obj({"name": {"type": "string", "maxLength": 80},
               "from_strategy": {"type": "boolean"},
               "adjustments": _obj(ADJUST)}, ["name"]),
         save_scenario, ("save_scenario",), writes=True, describe=_describe_save),
    Tool("create_plan", "Create a new plan (as a scenario) from answers gathered in conversation. "
         "Ask for what is missing; defaults fill the rest. Needs the person's approval.",
         _obj({"name": {"type": "string", "maxLength": 80}, "answers": _obj(INTAKE)}, ["answers"]),
         create_plan, ("save_scenario",), ("intake",), writes=True, describe=_describe_create),
]
BY_NAME = {t.name: t for t in TOOLS}


def enabled_tools(settings) -> list[Tool]:
    return [t for t in TOOLS if t.enabled(settings)]


def validate(tool: Tool, args: dict) -> str | None:
    """A reason the arguments are unacceptable, or None. Checks types and bounds of
    the schema's top-level properties - enough to keep the engine's inputs sane."""
    if not isinstance(args, dict):
        return "arguments must be an object"
    props = tool.schema.get("properties", {})
    for req in tool.schema.get("required", []):
        if req not in args:
            return f"'{req}' is required"
    for k, v in args.items():
        spec = props.get(k)
        if spec is None:
            return f"unknown argument '{k}'"
        t = spec.get("type")
        if t == "number" and (isinstance(v, bool) or not isinstance(v, (int, float))):
            return f"'{k}' must be a number"
        if t == "integer" and (isinstance(v, bool) or not isinstance(v, int)):
            return f"'{k}' must be a whole number"
        if t == "string" and not isinstance(v, str):
            return f"'{k}' must be text"
        if t == "boolean" and not isinstance(v, bool):
            return f"'{k}' must be true or false"
        if t == "object" and not isinstance(v, dict):
            return f"'{k}' must be an object"
        if t in ("number", "integer"):
            if "minimum" in spec and v < spec["minimum"]:
                return f"'{k}' must be at least {spec['minimum']}"
            if "maximum" in spec and v > spec["maximum"]:
                return f"'{k}' must be at most {spec['maximum']}"
        if "enum" in spec and v not in spec["enum"]:
            return f"'{k}' must be one of {', '.join(spec['enum'])}"
        if t == "object" and "properties" in spec:
            inner = validate(Tool(k, "", spec, None), v)
            if inner:
                return f"in '{k}': {inner}"
    return None
