"""Unit tests for the area data-scope value object and its application-layer helper
(US-007 ES-305: full-plant default scope).

Pure logic, no I/O — mirrors the style of ``test_resolve_permissions.py``. Narrowing to
a specific requested area (``?area=``) is ES-306 and is tested there once it exists.
"""

import dataclasses

from src.application.auth.resolve_permissions import area_scope_for_roles, resolve_query_scope
from src.domain.users_roles.entities import Role
from src.domain.users_roles.permissions import AreaScope


def _role(name="r", area_scope=None) -> Role:
    return Role.create_custom(
        name, permissions=["shift:read"], ad_groups=["G"], area_scope=area_scope
    )


# --- AreaScope ---------------------------------------------------------------


def test_full_plant_has_no_restriction():
    scope = AreaScope.of(None)
    assert scope.full_plant is True
    assert scope.areas is None


def test_of_normalizes_to_sorted_unique_tuple():
    scope = AreaScope.of(["Train 2", "Train 1", "Train 1"])
    assert scope.areas == ("Train 1", "Train 2")


def test_of_empty_list_means_full_plant():
    scope = AreaScope.of([])
    assert scope.full_plant is True
    assert scope.areas is None


def test_covers_is_true_for_everything_when_full_plant():
    scope = AreaScope.of(None)
    assert scope.covers("Train 1") is True
    assert scope.covers("anything") is True
    assert scope.covers(None) is True


def test_covers_none_is_false_for_a_scoped_role():
    """Matches pending_actions._in_scope: an arealess record is invisible to a scoped role."""
    scope = AreaScope.of(["Train 1"])
    assert scope.covers(None) is False


def test_covers_is_case_sensitive():
    scope = AreaScope.of(["Train 1"])
    assert scope.covers("Train 1") is True
    assert scope.covers("train 1") is False


def test_area_scope_is_frozen_and_hashable():
    scope = AreaScope.of(["Train 1"])
    try:
        scope.areas = ("Train 2",)  # type: ignore[misc]
        raised = False
    except dataclasses.FrozenInstanceError:
        raised = True
    assert raised
    assert hash(scope) == hash(AreaScope.of(["Train 1"]))
    assert {scope, AreaScope.of(["Train 1"])} == {scope}


# --- resolve_query_scope (default, no narrowing yet) --------------------------------


def test_resolve_query_scope_full_plant_returns_none():
    assert resolve_query_scope(None) is None


def test_resolve_query_scope_scoped_returns_the_roles_areas():
    assert resolve_query_scope(["Train 1"]) == ["Train 1"]
    assert resolve_query_scope(["T1", "T2"]) == ["T1", "T2"]


def test_resolve_query_scope_multi_role_union_is_unrestricted_if_any_role_is_full_plant():
    roles = [_role(area_scope=["Train 1"]), _role(area_scope=None)]
    unioned = area_scope_for_roles(roles)
    assert unioned is None
    assert resolve_query_scope(unioned) is None


def test_resolve_query_scope_multi_role_union_of_two_scoped_roles():
    roles = [_role(area_scope=["Train 1"]), _role(area_scope=["Train 2"])]
    unioned = area_scope_for_roles(roles)
    assert unioned == ["Train 1", "Train 2"]
    assert resolve_query_scope(unioned) == ["Train 1", "Train 2"]
