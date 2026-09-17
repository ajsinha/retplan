"""Route handlers, one module per area of the application.

    noauth_routes      - landing page, about, method notes
    plan_routes        - the plan editor: household, income, spending, debt,
                         accounts, wrappers, markets, tax, policy
    dashboard_routes   - the dashboard: KPIs, charts, verdict
    simulation_routes  - JSON API that runs the Monte Carlo and the solvers
    report_routes      - year-by-year cash flow, balance sheet, tax, audit
    export_routes      - download / upload a plan, download the workbook

Every handler is a class constructed with the FastAPI app and the plan store,
registering its own routes in ``_register_routes``.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from .noauth_routes import NoAuthRoutes
from .plan_routes import PlanRoutes
from .dashboard_routes import DashboardRoutes
from .simulation_routes import SimulationRoutes
from .report_routes import ReportRoutes
from .export_routes import ExportRoutes

__all__ = ["NoAuthRoutes", "PlanRoutes", "DashboardRoutes", "SimulationRoutes",
           "ReportRoutes", "ExportRoutes"]
