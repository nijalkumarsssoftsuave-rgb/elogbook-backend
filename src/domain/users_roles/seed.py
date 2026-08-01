"""The five base (system) roles — fixed platform data, not admin-editable.

This is the single source of truth for what ships by default; the MS SQL migration
(``migrations/0002_roles.sql``) inserts the same five rows by hand, since a SQL
migration cannot import Python. Keep the two in sync if a base role ever changes.
"""

from src.domain.users_roles.entities import Role

BASE_ROLES: list[Role] = [
    Role(
        id="base-operator",
        name="operator",
        is_custom=False,
        permissions=[
            "shift:read",
            "summary:read",
            "assistant:query",
            "action:read",
            "action:write",
        ],
        ad_groups=["OLNG-ELOG-OPERATORS"],
    ),
    Role(
        id="base-supervisor",
        name="supervisor",
        is_custom=False,
        permissions=[
            "shift:read",
            "summary:read",
            "summary:comment",
            "assistant:query",
            "action:read",
            "action:write",
            "action:confirm",
            "action:assign",
            "report:read",
        ],
        ad_groups=["OLNG-ELOG-SUPERVISORS"],
    ),
    Role(
        id="base-management",
        name="management",
        is_custom=False,
        permissions=[
            "shift:read",
            "summary:read",
            "assistant:query",
            "action:read",
            "report:read",
            "analytics:read",
        ],
        ad_groups=["OLNG-ELOG-SUPERINTENDENTS"],
    ),
    Role(
        id="base-administrator",
        name="administrator",
        is_custom=False,
        permissions=["*"],
        ad_groups=["OLNG-ELOG-ADMINS"],
    ),
    Role(
        id="base-super_user",
        name="super_user",
        is_custom=False,
        permissions=[
            "dashboard:configure",
            "widget:assign",
            "metric:control",
            "access:control",
            "user:read",
        ],
        ad_groups=["OLNG-ELOG-SUPERUSERS"],
    ),
]
