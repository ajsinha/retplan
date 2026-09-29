"""Help catalogue - the single source of truth for the help section.

One declarative list. The index renders searchable cards from it, each topic
self-registers a route, and the footer of every page builds its "related topics"
strip from the same data - so a topic lives in exactly one place and the
navigation cannot drift from the pages.

Each topic:
    slug      URL segment and template name (help/<slug>.html)
    title     card and page heading
    summary   one line on the card; also the page's standfirst
    icon      bootstrap-icons class
    keywords  extra search terms the card matches on
    context   optional plan-editor section this topic explains, which puts a
              contextual help link on that page

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

CATEGORIES = [
    {
        "id": "start",
        "name": "Start here",
        "icon": "bi-compass",
        "blurb": "Fifteen minutes from opening the app to a plan you believe.",
        "topics": [
            dict(slug="getting-started", title="Getting started", icon="bi-play-circle",
                 summary="The first fifteen minutes: what to enter, in what order, "
                         "and what to look at when you are done.",
                 keywords="first steps tutorial begin setup walkthrough"),
            dict(slug="quick-start", title="The quick-start wizard", icon="bi-magic",
                 summary="Six short steps from nothing to a complete plan, what each "
                         "answer becomes, and what the wizard assumes for you.",
                 keywords="wizard onboarding simple fast defaults new plan"),
            dict(slug="concepts", title="Five ideas that make this make sense",
                 icon="bi-lightbulb",
                 summary="Real terms, wrappers, the essential floor, sequence risk "
                         "and confidence. Understand these and the rest follows.",
                 keywords="concepts theory real nominal wrapper floor sequence"),
            dict(slug="recipes", title="Answering real questions", icon="bi-signpost-2",
                 summary="Step-by-step recipes: can I retire at 60, how much can I "
                         "spend, what if markets crash the year I stop working.",
                 keywords="how to workflow recipe scenario example questions"),
        ],
    },
    {
        "id": "plan",
        "name": "Building the plan",
        "icon": "bi-pencil-square",
        "blurb": "Every editor section, what each column means, and what to watch for.",
        "topics": [
            dict(slug="household", title="Household and timeline", icon="bi-people",
                 summary="Ages, retirement dates, how long to plan for, and the "
                         "spending smile.", context="household",
                 keywords="people ages retirement longevity horizon smile"),
            dict(slug="income", title="Income", icon="bi-arrow-down-circle",
                 summary="Salaries, pensions, rent, one-offs: growth basis, taxable "
                         "fraction, survivor continuation and probability.",
                 context="income",
                 keywords="salary pension rent inheritance state pension annuity"),
            dict(slug="spending", title="Spending", icon="bi-arrow-up-circle",
                 summary="Essential versus discretionary, category inflation, the age "
                         "curve, and lumpy costs that recur.", context="expenses",
                 keywords="expenses budget essential discretionary care education car"),
            dict(slug="debt", title="Debt", icon="bi-bank",
                 summary="Mortgages and loans, how they amortise, overpayments, and "
                         "the pay-off-versus-invest question.", context="debt",
                 keywords="mortgage loan amortisation interest overpayment payoff"),
            dict(slug="wrappers", title="Tax wrappers", icon="bi-shield-lock",
                 summary="The idea that makes the model jurisdiction-free: when money "
                         "is taxed, expressed as data. EET, TEE, TTE, ETT.",
                 context="wrappers",
                 keywords="EET TEE TTE ETT pension isa 401k roth generic tax treatment"),
            dict(slug="accounts", title="Accounts and allocation", icon="bi-wallet2",
                 summary="Balances, cost basis, asset mix, glidepaths, draw order and "
                         "employer matching.", context="accounts",
                 keywords="portfolio allocation glidepath rebalance draw order match"),
            dict(slug="markets", title="Markets, regimes and crashes",
                 icon="bi-graph-up-arrow",
                 summary="Expected returns, volatility, correlations, the regime "
                         "engine, the crash process, inflation and fees.",
                 context="markets",
                 keywords="returns volatility correlation regime bear bull crash "
                          "inflation fees monte carlo"),
            dict(slug="tax", title="Tax", icon="bi-percent",
                 summary="Bands in gross-income space, why allowances are bands, and "
                         "how the model answers 'what must I withdraw to spend X'.",
                 context="tax",
                 keywords="tax bands allowance taper marginal effective gross up"),
            dict(slug="policy", title="Withdrawal policy", icon="bi-sliders",
                 summary="The six spending rules, how guardrails behave, and what "
                         "counts as success.", context="policy",
                 keywords="withdrawal 4% rule guardrails vpw guyton klinger spending"),
            dict(slug="tools", title="Deciding: what-if, levers, and the planning tools",
                 icon="bi-sliders2",
                 summary="Sliders, ranked levers, claiming age, conversions, the spending "
                         "check, draw order, health and care, and net worth history.",
                 keywords="what if slider lever coach recommendation social security claiming "
                          "state pension delay roth conversion fill bracket decide guardrails "
                          "spending check withdrawal order draw order health medicare long "
                          "term care net worth history"),
            dict(slug="scenarios", title="Scenarios and comparison", icon="bi-layers",
                 summary="Keep several versions of the plan, switch between them, and "
                         "compare their odds and wealth side by side.",
                 keywords="scenario what if compare copy duplicate versions"),
        ],
    },
    {
        "id": "portfolio",
        "name": "Portfolios",
        "icon": "bi-briefcase",
        "blurb": "Every account you own and owe, real holdings priced daily, gathered "
                 "into portfolios and projected ten or more years ahead.",
        "topics": [
            dict(slug="portfolios", title="Accounts and portfolios", icon="bi-briefcase",
                 summary="Accounts - investments, cash, property, debts; holdings, "
                         "symbols, cost basis and asset classes; uploading and pasting; "
                         "portfolios as selections of accounts and of other portfolios; "
                         "currencies; the risk checks; linking a plan.",
                 keywords="holdings ticker symbol import csv paste allocation rebalance "
                          "xray concentration currency fx target excel xlsx upload "
                          "builder spreadsheet broker export isin account 401k ira roth "
                          "hsa brokerage checking savings home mortgage loan debt "
                          "property net worth link plan owner tax treatment "
                          "selection nested sub-portfolio many portfolios"),
            dict(slug="prices", title="Daily prices", icon="bi-cloud-download",
                 summary="Where prices come from, when they are collected, why only a "
                         "year is kept, and what to do when a symbol will not price.",
                 keywords="yahoo prices daily collector schedule retention history "
                          "securities lookup inquire admin administrator manual add "
                          "amend delete security"),
            dict(slug="projection", title="Projecting a portfolio", icon="bi-graph-up",
                 summary="The three return models, where each assumption comes from, "
                         "contributions and withdrawals, and how to read the fan chart "
                         "and the yearly or quarterly table.",
                 keywords="monte carlo projection simulation bootstrap gbm student t "
                          "percentile fan chart cagr drawdown quarterly annual"),
            dict(slug="stress-tests", title="Stress tests", icon="bi-lightning",
                 summary="Five historical crises replayed on your mix, and how to open "
                         "every projection with one to test sequence risk.",
                 keywords="stress test crisis 2008 dot com covid 2022 stagflation "
                          "sequence risk drawdown recovery"),
        ],
    },
    {
        "id": "answer",
        "name": "Reading the answer",
        "icon": "bi-speedometer2",
        "blurb": "What the numbers mean, and how much weight each one carries.",
        "topics": [
            dict(slug="dashboard", title="The dashboard", icon="bi-speedometer2",
                 summary="Every stat tile explained, including which are "
                         "deterministic and which come from the simulation.",
                 keywords="kpi tiles funded ratio verdict success terminal wealth"),
            dict(slug="simulation", title="Running a simulation", icon="bi-play-fill",
                 summary="Trials, seeds, error bars, and why 82% from 200 trials is "
                         "really 82% give or take five.",
                 keywords="monte carlo trials seed confidence standard error"),
            dict(slug="charts", title="Reading the charts", icon="bi-bar-chart-line",
                 summary="How to read the fan chart, the spaghetti plot, the "
                         "histogram, the sweep and the tornado - and the traps in each.",
                 keywords="fan chart percentile spaghetti histogram tornado sweep"),
            dict(slug="solvers", title="The solvers", icon="bi-cpu",
                 summary="Maximum sustainable spend, earliest retirement age and the "
                         "saving needed - what they optimise and what they assume.",
                 keywords="solver goal seek max spend earliest retirement bisection"),
            dict(slug="reports", title="Reports", icon="bi-table",
                 summary="The year-by-year cash flow, balance sheet and tax tables, "
                         "and what to check in each.",
                 keywords="cashflow balance sheet tax table year by year"),
            dict(slug="audit", title="The audit", icon="bi-clipboard-check",
                 summary="What each check proves, why the roll-forward identity is "
                         "the important one, and what to do when something fails.",
                 keywords="audit checks reconciliation validation errors"),
        ],
    },
    {
        "id": "reference",
        "name": "Reference",
        "icon": "bi-journal-text",
        "blurb": "Definitions, limits, fixes, and how RetPlan is installed and run.",
        "topics": [
            dict(slug="glossary", title="Glossary", icon="bi-journal-text",
                 summary="Every term the app uses, defined in one line each.",
                 keywords="definitions terms vocabulary meaning"),
            dict(slug="limitations", title="What this model does not do",
                 icon="bi-exclamation-triangle",
                 summary="The honest list: simplifications, omissions, and where the "
                         "answer will be wrong.",
                 keywords="limitations caveats assumptions weaknesses accuracy"),
            dict(slug="troubleshooting", title="Troubleshooting", icon="bi-tools",
                 summary="Numbers that look wrong, edits that seem not to apply, and "
                         "runs that fail - with the usual cause of each.",
                 keywords="problem wrong error stale broken help fix"),
            dict(slug="system", title="System and database", icon="bi-hdd-stack",
                 summary="The configuration file, SQLite or PostgreSQL, the two schema "
                         "files, and where your data lives.",
                 keywords="database sqlite postgres postgresql config toml schema "
                          "backup install settings"),
        ],
    },
]

TOPICS = {t["slug"]: dict(t, category=c["name"], category_id=c["id"])
          for c in CATEGORIES for t in c["topics"]}
ORDER = list(TOPICS)

# plan-editor section -> the topic that explains it
CONTEXT_HELP = {t["context"]: slug for slug, t in TOPICS.items() if t.get("context")}


def siblings(slug: str, limit: int = 8) -> list:
    """Other topics in the same category, for the page footer."""
    topic = TOPICS.get(slug)
    if not topic:
        return []
    return [t for t in TOPICS.values()
            if t["category"] == topic["category"] and t["slug"] != slug][:limit]


def related(slug: str) -> dict:
    topic = TOPICS.get(slug, {})
    i = ORDER.index(slug) if slug in ORDER else -1
    return {"category": topic.get("category", ""),
            "category_id": topic.get("category_id", ""),
            "siblings": siblings(slug), "topic": topic,
            "prev": TOPICS[ORDER[i - 1]] if i > 0 else None,
            "next": TOPICS[ORDER[i + 1]] if 0 <= i < len(ORDER) - 1 else None}


def search(q: str) -> list:
    """Topics matching every word of ``q`` in title, summary or keywords."""
    words = [w for w in q.lower().split() if w]
    out = []
    for t in TOPICS.values():
        hay = f"{t['title']} {t['summary']} {t.get('keywords', '')}".lower()
        if words and all(w in hay for w in words):
            out.append(t)
    return out


# Long-form guides, rendered from web/guides/<slug>.md (web/guide_render.py):
# tutorials that build on each other, and catalogues that list everything.
GUIDES = [
    dict(slug="first-decision", kind="tutorial", icon="signpost-split",
         title="From nothing to a decision in twenty minutes",
         summary="Build a plan with the wizard, read the answer, find your biggest levers, "
                 "combine them and keep the change worth making."),
    dict(slug="portfolio-tutorial", kind="tutorial", icon="file-earmark-arrow-up",
         title="From a broker export to a ten-year projection",
         summary="Upload positions, review the matches and accounts, add the rest, gather "
                 "them into a portfolio, check it, project it, stress it and link your "
                 "plan to it."),
    dict(slug="configuration", kind="catalogue", icon="sliders",
         title="Configuration reference",
         summary="Every setting in config/retplan.toml and every environment variable, "
                 "with its default and what it does."),
    dict(slug="api", kind="catalogue", icon="braces",
         title="HTTP API reference",
         summary="The JSON endpoints behind the pages: simulation, what-if, levers, "
                 "portfolios, symbol search, plans as files, health."),
]


def guide(slug: str) -> dict | None:
    for i, g in enumerate(GUIDES):
        if g["slug"] == slug:
            return dict(g, prev=GUIDES[i - 1] if i else None,
                        next=GUIDES[i + 1] if i < len(GUIDES) - 1 else None)
    return None
