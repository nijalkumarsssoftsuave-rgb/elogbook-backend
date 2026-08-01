"""Unit tests for the area data-scope value object and its application-layer helper
(US-007 ES-305/306: default scope + narrowing by requested area).

Pure logic, no I/O — mirrors the style of ``test_resolve_permissions.py``.
"""

import dataclasses

import pytest

from src.api.errors.exceptions import ForbiddenError
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


def test_narrowed_to_in_scope_returns_single_area_scope():
    scope = AreaScope.of(["Train 1", "Train 2"])
    narrowed = scope.narrowed_to("Train 1")
    assert narrowed is not None
    assert narrowed.areas == ("Train 1",)


def test_narrowed_to_out_of_scope_returns_none_not_exception():
    scope = AreaScope.of(["Train 1"])
    assert scope.narrowed_to("Train 2") is None


def test_narrowed_to_from_full_plant_returns_requested_area():
    scope = AreaScope.of(None)
    narrowed = scope.narrowed_to("Train 1")
    assert narrowed is not None
    assert narrowed.areas == ("Train 1",)


# --- resolve_query_scope, default (ES-305) -------------------------------------------


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


# --- resolve_query_scope, narrowing (ES-306) ------------------------------------------


@pytest.mark.parametrize(
    "area_scope, requested_area, expected",
    [
        (None, None, None),
        (None, "Train 1", ["Train 1"]),
        (["Train 1"], None, ["Train 1"]),
        (["Train 1"], "Train 1", ["Train 1"]),
        (["T1", "T2"], None, ["T1", "T2"]),
    ],
)
def test_resolve_query_scope_truth_table(area_scope, requested_area, expected):
    assert resolve_query_scope(area_scope, requested_area) == expected


def test_resolve_query_scope_out_of_scope_raises_forbidden():
    with pytest.raises(ForbiddenError) as exc_info:
        resolve_query_scope(["Train 1"], "Train 2")
    assert exc_info.value.status_code == 403


def test_resolve_query_scope_is_case_sensitive():
    with pytest.raises(ForbiddenError):
        resolve_query_scope(["Train 1"], "train 1")


def test_resolve_query_scope_multi_role_union_then_narrow():
    """Union two scoped roles via area_scope_for_roles, then resolve a request scope."""
    roles = [_role(area_scope=["Train 1"]), _role(area_scope=["Train 2"])]
    unioned = area_scope_for_roles(roles)
    assert unioned == ["Train 1", "Train 2"]

    assert resolve_query_scope(unioned, None) == ["Train 1", "Train 2"]
    assert resolve_query_scope(unioned, "Train 1") == ["Train 1"]
    with pytest.raises(ForbiddenError):
        resolve_query_scope(unioned, "Train 3")


def test_resolve_query_scope_multi_role_union_with_full_plant_role_is_unrestricted():
    roles = [_role(area_scope=["Train 1"]), _role(area_scope=None)]
    unioned = area_scope_for_roles(roles)
    assert unioned is None
    assert resolve_query_scope(unioned, "Anywhere") == ["Anywhere"]
