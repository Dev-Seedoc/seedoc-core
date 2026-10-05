"""Tenant aggregate. ORM classes (`Tenant`, `TenantMember`, `TenantDomain`, `Invitation`) arrive with migration 0001."""

from enum import StrEnum


class MemberRole(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    EDITOR = "editor"
