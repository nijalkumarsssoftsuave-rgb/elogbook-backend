"""Role domain entity — pure business data, no framework or I/O.

A role grants a set of permissions to whoever holds it, is mapped from one or more AD
groups, and may optionally be restricted to a set of areas (BRD: full-plant visibility
for operational roles, area scope for restricted custom roles). Five **base** roles
(Operator, Supervisor, Management, Administrator, Super User) ship as fixed system data;
Administrators create additional **custom** roles through the admin API. Base roles
cannot be edited or deleted through the API — see ``application/admin/manage_roles.py``.
"""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass
class Role:
    """A named set of permissions, optionally area-scoped, mapped from AD groups."""

    id: str
    name: str
    is_custom: bool
    permissions: list[str]
    ad_groups: list[str]
    area_scope: list[str] | None = None  # None = full plant
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @staticmethod
    def create_custom(
        name: str,
        permissions: list[str],
        ad_groups: list[str],
        area_scope: list[str] | None = None,
    ) -> "Role":
        """An Admin-defined custom role. Always ``is_custom=True``."""
        return Role(
            id=uuid.uuid4().hex,
            name=name,
            is_custom=True,
            permissions=sorted(set(permissions)),
            ad_groups=sorted(set(ad_groups)),
            area_scope=sorted(set(area_scope)) if area_scope else None,
        )

    def touch(self) -> None:
        self.updated_at = datetime.now(UTC)
