"""Unit tests for JWT-based token validation — signature, issuer, audience, expiry,
and role/permission/area-scope resolution via the role repository.
"""

from datetime import UTC, datetime, timedelta

import jwt
import pytest

from src.api.errors.exceptions import UnauthorizedError
from src.application.audit.recorder import AuditEntry, AuditRecorder
from src.core.config import get_settings
from src.domain.users_roles.entities import Role
from src.infrastructure.auth import dev_issuer, token_validator
from src.infrastructure.persistence.in_memory_roles import InMemoryRoleRepository


@pytest.fixture
def role_repo():
    return InMemoryRoleRepository()


class SpyAuditRecorder(AuditRecorder):
    """Records entries in memory so tests can assert what was audited."""

    def __init__(self) -> None:
        self.entries: list[AuditEntry] = []

    async def record(self, entry: AuditEntry) -> None:
        self.entries.append(entry)


@pytest.fixture
def audit_spy():
    return SpyAuditRecorder()


def _sign(claims: dict) -> str:
    settings = get_settings()
    private_pem, _ = dev_issuer._ensure_keypair(settings)
    return jwt.encode(
        claims, private_pem, algorithm=dev_issuer.ALGORITHM, headers={"kid": dev_issuer.DEV_KEY_ID}
    )


def _valid_claims(**overrides) -> dict:
    settings = get_settings()
    now = datetime.now(UTC)
    claims = {
        "sub": "dev|jane.operator",
        "preferred_username": "jane.operator",
        "name": "Jane Operator",
        "groups": ["OLNG-ELOG-OPERATORS"],
        "iss": settings.auth_issuer,
        "aud": settings.auth_audience,
        "iat": now,
        "exp": now + timedelta(minutes=15),
    }
    claims.update(overrides)
    return claims


async def test_valid_token_resolves_principal_and_role(role_repo):
    token, _ = dev_issuer.mint_token(
        get_settings(), username="jane.operator", groups=["OLNG-ELOG-OPERATORS"]
    )
    principal = await token_validator.validate_token(f"Bearer {token}", role_repo)
    assert principal.username == "jane.operator"
    assert principal.roles == ["operator"]
    assert "action:write" in principal.permissions
    assert principal.area_scope is None  # base role -> full plant


async def test_multi_group_user_gets_every_mapped_role_and_permission_union(role_repo):
    token, _ = dev_issuer.mint_token(
        get_settings(),
        username="mo.dual",
        groups=["OLNG-ELOG-OPERATORS", "OLNG-ELOG-SUPERVISORS"],
    )
    principal = await token_validator.validate_token(f"Bearer {token}", role_repo)
    assert principal.roles == ["operator", "supervisor"]
    assert "action:assign" in principal.permissions  # supervisor-only permission present


async def test_administrator_gets_wildcard_permission(role_repo):
    token, _ = dev_issuer.mint_token(
        get_settings(), username="admin.user", groups=["OLNG-ELOG-ADMINS"]
    )
    principal = await token_validator.validate_token(f"Bearer {token}", role_repo)
    assert principal.permissions == ["*"]


async def test_unmapped_group_is_denied_access(role_repo):
    token, _ = dev_issuer.mint_token(get_settings(), username="ghost", groups=["UNMAPPED-GROUP"])
    with pytest.raises(UnauthorizedError, match="not mapped to any platform role"):
        await token_validator.validate_token(f"Bearer {token}", role_repo)


async def test_valid_token_with_no_groups_at_all_is_denied_access(role_repo):
    token, _ = dev_issuer.mint_token(get_settings(), username="nogroups", groups=[])
    with pytest.raises(UnauthorizedError, match="not mapped to any platform role"):
        await token_validator.validate_token(f"Bearer {token}", role_repo)


async def test_area_scoped_custom_role_narrows_area_scope(role_repo):
    scoped = Role.create_custom(
        "train1_operator",
        permissions=["action:read"],
        ad_groups=["TRAIN1-GROUP"],
        area_scope=["Train 1"],
    )
    await role_repo.add(scoped)
    token, _ = dev_issuer.mint_token(get_settings(), username="area.user", groups=["TRAIN1-GROUP"])
    principal = await token_validator.validate_token(f"Bearer {token}", role_repo)
    assert principal.area_scope == ["Train 1"]


async def test_missing_authorization_header_is_unauthorized(role_repo):
    with pytest.raises(UnauthorizedError):
        await token_validator.validate_token(None, role_repo)


async def test_malformed_header_is_unauthorized(role_repo):
    with pytest.raises(UnauthorizedError):
        await token_validator.validate_token("not-a-bearer-token", role_repo)


async def test_expired_token_is_rejected(role_repo):
    now = datetime.now(UTC)
    token = _sign(_valid_claims(iat=now - timedelta(hours=1), exp=now - timedelta(minutes=1)))
    with pytest.raises(UnauthorizedError):
        await token_validator.validate_token(f"Bearer {token}", role_repo)


async def test_wrong_issuer_is_rejected(role_repo):
    token = _sign(_valid_claims(iss="https://not-the-real-issuer.local"))
    with pytest.raises(UnauthorizedError):
        await token_validator.validate_token(f"Bearer {token}", role_repo)


async def test_wrong_audience_is_rejected(role_repo):
    token = _sign(_valid_claims(aud="not-elogbook"))
    with pytest.raises(UnauthorizedError):
        await token_validator.validate_token(f"Bearer {token}", role_repo)


async def test_tampered_signature_is_rejected(role_repo):
    token, _ = dev_issuer.mint_token(get_settings(), username="jane.operator", groups=[])
    tampered = token[:-4] + ("AAAA" if not token.endswith("AAAA") else "BBBB")
    with pytest.raises(UnauthorizedError):
        await token_validator.validate_token(f"Bearer {tampered}", role_repo)


async def test_live_mode_not_yet_implemented(monkeypatch, role_repo):
    settings = get_settings()
    monkeypatch.setattr(settings, "auth_stub_enabled", False)
    token, _ = dev_issuer.mint_token(settings, username="jane.operator", groups=[])
    with pytest.raises(UnauthorizedError, match="Live AD FS"):
        await token_validator.validate_token(f"Bearer {token}", role_repo)


# --- BE-US001-6: every sign-in attempt is written to the audit trail ---


async def test_successful_signin_is_audited(role_repo, audit_spy):
    token, _ = dev_issuer.mint_token(
        get_settings(), username="jane.operator", groups=["OLNG-ELOG-OPERATORS"]
    )
    await token_validator.validate_token(f"Bearer {token}", role_repo, audit_spy)

    assert len(audit_spy.entries) == 1
    entry = audit_spy.entries[0]
    assert entry.actor == "jane.operator"
    assert entry.action == "auth.signin.success"
    assert entry.payload["roles"] == ["operator"]


async def test_unmapped_group_denial_is_audited(role_repo, audit_spy):
    token, _ = dev_issuer.mint_token(get_settings(), username="ghost", groups=["UNMAPPED-GROUP"])
    with pytest.raises(UnauthorizedError):
        await token_validator.validate_token(f"Bearer {token}", role_repo, audit_spy)

    assert len(audit_spy.entries) == 1
    entry = audit_spy.entries[0]
    assert entry.actor == "ghost"
    assert entry.action == "auth.signin.denied"
    assert entry.payload["reason"] == "no_role_mapped_for_groups"


async def test_missing_header_denial_is_audited(role_repo, audit_spy):
    with pytest.raises(UnauthorizedError):
        await token_validator.validate_token(None, role_repo, audit_spy)

    assert len(audit_spy.entries) == 1
    entry = audit_spy.entries[0]
    assert entry.actor == "unknown"
    assert entry.action == "auth.signin.denied"
    assert entry.payload["reason"] == "missing_or_malformed_authorization_header"


async def test_invalid_token_denial_is_audited(role_repo, audit_spy):
    token, _ = dev_issuer.mint_token(get_settings(), username="jane.operator", groups=[])
    tampered = token[:-4] + ("AAAA" if not token.endswith("AAAA") else "BBBB")
    with pytest.raises(UnauthorizedError):
        await token_validator.validate_token(f"Bearer {tampered}", role_repo, audit_spy)

    assert len(audit_spy.entries) == 1
    entry = audit_spy.entries[0]
    assert entry.actor == "unknown"
    assert entry.action == "auth.signin.denied"
    assert entry.payload["reason"] == "invalid_token"


async def test_validate_token_without_audit_arg_still_works(role_repo):
    """Existing callers that don't pass an audit recorder default to a no-op."""
    token, _ = dev_issuer.mint_token(
        get_settings(), username="jane.operator", groups=["OLNG-ELOG-OPERATORS"]
    )
    principal = await token_validator.validate_token(f"Bearer {token}", role_repo)
    assert principal.username == "jane.operator"
