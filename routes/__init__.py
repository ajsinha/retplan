"""Route handlers, one module per area of the application.

    noauth_routes      - landing page, about, method, search, system
    wizard_routes      - the quick-start wizard (/start)
    scenario_routes    - named plan scenarios and the side-by-side comparison
    plan_routes        - the plan editor: household, income, spending, debt,
                         accounts, wrappers, markets, tax, policy
    dashboard_routes   - the dashboard: KPIs, charts, verdict
    simulation_routes  - JSON API that runs the Monte Carlo and the solvers
    report_routes      - year-by-year cash flow, balance sheet, tax, audit
    export_routes      - download / upload a plan
    account_routes     - accounts of every kind, their holdings and values
    portfolio_routes   - portfolios (selections of accounts), prices, projections, stress
    builder_routes     - the portfolio builder: upload a spreadsheet, review, import
    market_routes      - market data: securities collected daily, held or not
    security_routes    - securities: lookup for anyone; add, amend, delete for admins
    admin_routes       - administrator sign-in, sign-out and password change
    strategy_routes    - the strategy optimiser: every decision chosen together
    tools_routes       - what-if, levers, claiming, conversions, spending check,
                         draw order, health and care
    networth_routes    - net worth over time: every account, and each portfolio
    help_routes        - the help section, rendered from web/help_catalog.py

Every handler is a class constructed with the FastAPI app and the plan store,
registering its own routes in ``_register_routes``; anything else it needs is on
``app.state``.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from .noauth_routes import NoAuthRoutes
from .wizard_routes import WizardRoutes
from .scenario_routes import ScenarioRoutes
from .plan_routes import PlanRoutes
from .dashboard_routes import DashboardRoutes
from .simulation_routes import SimulationRoutes
from .report_routes import ReportRoutes
from .export_routes import ExportRoutes
from .builder_routes import BuilderRoutes
from .account_routes import AccountRoutes
from .portfolio_routes import PortfolioRoutes
from .market_routes import MarketRoutes
from .security_routes import SecurityRoutes
from .admin_routes import AdminRoutes
from .strategy_routes import StrategyRoutes
from .tools_routes import ToolsRoutes
from .networth_routes import NetWorthRoutes
from .help_routes import HelpRoutes

ALL_ROUTES = (NoAuthRoutes, WizardRoutes, ScenarioRoutes, PlanRoutes, DashboardRoutes,
              SimulationRoutes, ReportRoutes, ExportRoutes, BuilderRoutes, AccountRoutes,
              PortfolioRoutes,
              MarketRoutes, SecurityRoutes, AdminRoutes, StrategyRoutes, ToolsRoutes,
              NetWorthRoutes,
              HelpRoutes)

__all__ = ["ALL_ROUTES", "NoAuthRoutes", "WizardRoutes", "ScenarioRoutes", "PlanRoutes",
           "DashboardRoutes", "SimulationRoutes", "ReportRoutes", "ExportRoutes",
           "BuilderRoutes", "AccountRoutes", "PortfolioRoutes", "MarketRoutes", "SecurityRoutes", "AdminRoutes", "StrategyRoutes", "ToolsRoutes", "NetWorthRoutes", "HelpRoutes"]
