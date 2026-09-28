"""One authentication contract for the dashboard and managed HTTPS wrappers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypedDict

from app.core.exceptions import DashboardConflictError

PolicyMode = Literal["standard", "managed"]


class PolicyCapabilities(TypedDict):
    mode: PolicyMode
    adminPasswordRequired: bool
    apiKeyAuthRequired: bool
    guestPassword: Literal["optional"]


class PolicyState(TypedDict):
    password_configured: bool
    api_key_auth_enabled: bool
    guest_access_enabled: bool
    guest_password_configured: bool


class PolicySnapshot(TypedDict):
    schemaVersion: Literal[1]
    mode: PolicyMode
    requirements: PolicyCapabilities
    state: PolicyState
    allowed: bool
    violations: list[str]


@dataclass(frozen=True)
class AuthState:
    password_configured: bool
    api_key_auth_enabled: bool
    guest_access_enabled: bool
    guest_password_configured: bool


@dataclass(frozen=True)
class DeploymentAuthPolicy:
    mode: PolicyMode

    @property
    def admin_password_required(self) -> bool:
        return self.mode == "managed"

    @property
    def api_key_auth_required(self) -> bool:
        return self.mode == "managed"

    @property
    def guest_password(self) -> Literal["optional"]:
        return "optional"

    def violations(self, state: AuthState) -> list[str]:
        violations = []
        if self.admin_password_required and not state.password_configured:
            violations.append("admin_password_required")
        if self.api_key_auth_required and not state.api_key_auth_enabled:
            violations.append("api_key_auth_required")
        return violations

    def validate_api_key_update(self, enabled: bool | None) -> None:
        if self.api_key_auth_required and enabled is False:
            raise DashboardConflictError(
                "This deployment requires API key authentication to remain enabled.",
                code="deployment_policy_violation",
                param="apiKeyAuthEnabled",
            )

    def validate_password_removal(self) -> None:
        if self.admin_password_required:
            raise DashboardConflictError(
                "This deployment requires an administrator password. You can change it, but cannot remove it.",
                code="deployment_policy_violation",
                param="password",
            )

    def capabilities(self) -> PolicyCapabilities:
        return {
            "mode": self.mode,
            "adminPasswordRequired": self.admin_password_required,
            "apiKeyAuthRequired": self.api_key_auth_required,
            "guestPassword": self.guest_password,
        }

    def snapshot(self, state: AuthState) -> PolicySnapshot:
        violations = self.violations(state)
        return {
            "schemaVersion": 1,
            "mode": self.mode,
            "requirements": self.capabilities(),
            "state": {
                "password_configured": state.password_configured,
                "api_key_auth_enabled": state.api_key_auth_enabled,
                "guest_access_enabled": state.guest_access_enabled,
                "guest_password_configured": state.guest_password_configured,
            },
            "allowed": not violations,
            "violations": violations,
        }


def get_deployment_auth_policy() -> DeploymentAuthPolicy:
    from app.core.config.settings import get_settings

    return DeploymentAuthPolicy(get_settings().deployment_auth_policy)
