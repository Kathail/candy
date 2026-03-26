def register_blueprints(app):
    from app.routes import (
        admin, analytics, api, auth, balances, customers,
        danger, dashboard, exports, leads, planner, reports, route,
    )
    for module in [
        auth, admin, dashboard, customers, route, planner,
        balances, analytics, leads, reports, api, exports, danger,
    ]:
        app.register_blueprint(module.bp)
