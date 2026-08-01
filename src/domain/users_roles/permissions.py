"""Permission catalogue — the enumerated set of selectable module permissions.

Every permission string that can be assigned to a custom role must appear here.
The wildcard ``*`` is intentionally excluded — it is reserved for the built-in
administrator role and is not a user-selectable catalogue entry.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class PermissionEntry:
    permission: str
    module: str
    description: str


PERMISSION_CATALOGUE: list[PermissionEntry] = [
    # shift
    PermissionEntry("shift:read", "shift", "View shift records"),
    # summary
    PermissionEntry("summary:read", "summary", "View shift summaries"),
    PermissionEntry("summary:comment", "summary", "Add comments to shift summaries"),
    # assistant
    PermissionEntry("assistant:query", "assistant", "Query the AI assistant"),
    # action
    PermissionEntry("action:read", "action", "View pending actions"),
    PermissionEntry("action:write", "action", "Capture new pending actions"),
    PermissionEntry("action:confirm", "action", "Confirm completed actions"),
    PermissionEntry("action:assign", "action", "Assign actions to users"),
    # report
    PermissionEntry("report:read", "report", "View reports"),
    # analytics
    PermissionEntry("analytics:read", "analytics", "View analytics data"),
    # dashboard
    PermissionEntry("dashboard:configure", "dashboard", "Configure dashboard layout"),
    # widget
    PermissionEntry("widget:assign", "widget", "Assign widgets to dashboards"),
    # metric
    PermissionEntry("metric:control", "metric", "Control metric display settings"),
    # access
    PermissionEntry("access:control", "access", "Manage access control settings"),
    # user
    PermissionEntry("user:read", "user", "View user records"),
    PermissionEntry("user:manage", "user", "Create, update and delete users"),
    # role
    PermissionEntry("role:read", "role", "View roles and the permission catalogue"),
    PermissionEntry("role:manage", "role", "Create, update and delete custom roles"),
]

VALID_PERMISSIONS: frozenset[str] = frozenset(e.permission for e in PERMISSION_CATALOGUE)
