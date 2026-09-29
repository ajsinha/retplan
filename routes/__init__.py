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
    portfolio_routes   - portfolios, holdings, prices, projections, stress tests
    builder_routes     - the portfolio builder: upload a spreadsheet, review, import
    security_routes    - securities: lookup for anyone; add, amend, delete for admins
    admin_routes       - administrator sign-in, sign-out and password change
    tools_routes       - what-if, levers, claiming-age and conversion explorers
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
from .portfolio_routes import PortfolioRoutes
from .security_routes import SecurityRoutes
from .admin_routes import AdminRoutes
from .tools_routes import ToolsRoutes
from .help_routes import HelpRoutes

ALL_ROUTES = (NoAuthRoutes, WizardRoutes, ScenarioRoutes, PlanRoutes, DashboardRoutes,
              SimulationRoutes, ReportRoutes, ExportRoutes, BuilderRoutes, PortfolioRoutes,
              SecurityRoutes, AdminRoutes, ToolsRoutes,
              HelpRoutes)

__all__ = ["ALL_ROUTES", "NoAuthRoutes", "WizardRoutes", "ScenarioRoutes", "PlanRoutes",
           "DashboardRoutes", "SimulationRoutes", "ReportRoutes", "ExportRoutes",
           "BuilderRoutes", "PortfolioRoutes", "SecurityRoutes", "AdminRoutes", "ToolsRoutes", "HelpRoutes"]
