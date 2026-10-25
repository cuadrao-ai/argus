"""Canonical Business roles and their permissions."""

from enum import Enum
from types import MappingProxyType
from typing import Literal

Permission = Literal[
    "read", "prepare", "approve", "manage", "download", "export", "assign_owner"
]


class BusinessRole(str, Enum):
    OWNER = "owner"
    ADMIN = "admin"
    EDITOR = "editor"
    VIEWER = "viewer"


ROLE_PERMISSIONS = MappingProxyType(
    {
        BusinessRole.OWNER: frozenset(
            {"read", "prepare", "approve", "manage", "download", "export", "assign_owner"}
        ),
        BusinessRole.ADMIN: frozenset(
            {"read", "prepare", "manage", "download", "export"}
        ),
        BusinessRole.EDITOR: frozenset({"read", "prepare", "download", "export"}),
        BusinessRole.VIEWER: frozenset({"read"}),
    }
)


def legacy_capabilities(role: BusinessRole) -> tuple[str, ...]:
    return tuple(c for c in ("read", "prepare", "approve") if c in ROLE_PERMISSIONS[role])


def legacy_role(role: BusinessRole) -> Literal["owner", "accountant"]:
    return "owner" if role == BusinessRole.OWNER else "accountant"


def promotion_requires_acceptance(current: BusinessRole, requested: BusinessRole) -> bool:
    order = tuple(BusinessRole)
    return requested in (BusinessRole.OWNER, BusinessRole.ADMIN) and order.index(
        requested
    ) < order.index(current)
