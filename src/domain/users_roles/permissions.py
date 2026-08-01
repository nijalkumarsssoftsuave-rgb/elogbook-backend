"""Data-scope value object — pure business rule, no framework or I/O.

``AreaScope`` captures "which plant areas is this caller's data restricted to" (BRD:
full-plant visibility by default; area scope only for roles specifically configured with
one — see ``Role.area_scope`` and ``area_scope_for_roles``). This module must not import
anything from the API layer (clean-architecture dependency rule): callers that need to
turn an out-of-scope request into an HTTP error do that translation themselves.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class AreaScope:
    """A caller's data-visibility restriction. ``areas=None`` means full plant."""

    areas: tuple[str, ...] | None = None  # None = full plant

    @staticmethod
    def of(areas: list[str] | None) -> "AreaScope":
        """Build a scope from a role's (or resolved principal's) area list.

        A falsy value (``None`` or ``[]``) means full plant — matching
        ``area_scope_for_roles()``'s ``sorted(scope) if scope else None`` and
        ``Role.create_custom()``'s identical normalization: an empty restriction has
        always meant full plant in this codebase, never "restricted to nothing".
        """
        return AreaScope(tuple(sorted(set(areas))) if areas else None)

    @property
    def full_plant(self) -> bool:
        """True when this scope carries no area restriction."""
        return self.areas is None

    def covers(self, area: str | None) -> bool:
        """True if a record/request for ``area`` is visible under this scope.

        Full-plant covers everything, including records with no area at all. A scoped
        role, however, does NOT cover ``area=None`` — an arealess record is invisible to
        it, byte-matching ``src/api/v1/pending_actions.py``'s existing
        ``_in_scope(area, area_scope) -> area_scope is None or area in area_scope``.
        Matching is exact and case-sensitive (e.g. "Train 1" != "train 1").
        """
        if self.areas is None:
            return True
        return area is not None and area in self.areas

    def narrowed_to(self, requested: str) -> "AreaScope | None":
        """The single-area scope for ``requested``, or ``None`` if out of scope.

        Returns ``None`` as a sentinel rather than raising — this is the domain layer,
        which must not import api-layer exceptions; the caller (application layer)
        turns ``None`` into a 403 (ES-306, ``resolve_query_scope``).
        """
        return AreaScope((requested,)) if self.covers(requested) else None

    def as_list(self) -> list[str] | None:
        """This scope's areas as a plain list, for embedding in responses/DTOs."""
        return None if self.areas is None else list(self.areas)
