"""Request/response schemas for customers, deliveries and machines (API.md §3.5)."""

import re
from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import AfterValidator, BaseModel, Field, StringConstraints, field_validator

from seedoc.models.deliveries import DeliveryKind, DeliveryStatus
from seedoc.schemas.common import Name, RequiredLanguages

# Deliberately loose (API.md §3.5: "must look like an address"); the address is only shown, never mailed by us.
_EMAIL_PATTERN = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


def _check_email(value: str) -> str:
    if not _EMAIL_PATTERN.fullmatch(value):
        raise ValueError("not an e-mail address")
    return value.lower()


ContactEmail = Annotated[str, StringConstraints(strip_whitespace=True, max_length=320), AfterValidator(_check_email)]
# Order and serial numbers are the manufacturer's own codes: trimmed, never empty.
Code = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
SortOrder = Annotated[int, Field(ge=0, le=2_147_483_647)]


def _reject_null(value: object) -> object:
    if value is None:
        raise ValueError("cannot be null; leave the field out to keep it")
    return value


# ─────────────────────────── customers ───────────────────────────


class CustomerCreate(BaseModel):
    name: Name
    contact_name: Name | None = None
    contact_email: ContactEmail | None = None


class CustomerUpdate(BaseModel):
    """A field left out stays as it is; `null` clears the contact fields and is a 422 for `name`."""

    name: Name | None = None
    contact_name: Name | None = None
    contact_email: ContactEmail | None = None

    _name_not_null = field_validator("name", mode="before")(_reject_null)


class CustomerRead(BaseModel):
    id: UUID
    name: str
    contact_name: str | None
    contact_email: str | None
    delivery_count: int
    created_at: datetime
    updated_at: datetime


# ─────────────────────────── machines ───────────────────────────


class MachineCreate(BaseModel):
    product_id: UUID
    name: Name
    serial_no: Code


class MachineUpdate(BaseModel):
    """A field left out stays as it is; `null` is a 422. Product and delivery never change."""

    name: Name | None = None
    serial_no: Code | None = None
    sort_order: SortOrder | None = None

    _not_null = field_validator("name", "serial_no", "sort_order", mode="before")(_reject_null)


class MachineListItem(BaseModel):
    """A machine inside `DeliveryRead.machines` (`MachineRead` without `delivery_id`)."""

    id: UUID
    product_id: UUID
    product_name: str
    name: str
    serial_no: str
    public_token: str  # machine QR, `/m/{token}`; never changes
    portal_url: str
    first_published_at: datetime | None
    archived_at: datetime | None


class MachineRead(MachineListItem):
    delivery_id: UUID


class MachineDocumentAttach(BaseModel):
    """Body of `attach_machine_document`: the document that becomes specific to this machine."""

    document_id: UUID


# ─────────────────────────── deliveries ───────────────────────────


class DeliveryCreate(BaseModel):
    """Without `required_languages` the delivery starts with `[]`; each machine added while it is a draft appends its
    product's languages (API.md §3.5)."""

    customer_id: UUID
    kind: DeliveryKind
    name: Name
    order_no: Code | None = None
    required_languages: RequiredLanguages | None = None


class DeliveryUpdate(BaseModel):
    """A field left out stays as it is; `null` clears `order_no` and is a 422 for `name` and `required_languages`.
    Customer and kind never change."""

    name: Name | None = None
    order_no: Code | None = None
    required_languages: RequiredLanguages | None = None

    _not_null = field_validator("name", "required_languages", mode="before")(_reject_null)


class DeliveryListQuery(BaseModel):
    """Filters of `list_deliveries`; both optional, combined with AND."""

    customer_id: UUID | None = None
    status: DeliveryStatus | None = None


class DeliveryListItem(BaseModel):
    id: UUID
    customer_id: UUID
    customer_name: str
    kind: DeliveryKind
    name: str
    order_no: str | None
    status: DeliveryStatus
    machine_count: int
    current_release_no: int | None  # null until the release tables exist (M2-B4)
    updated_at: datetime


class DeliveryRead(BaseModel):
    id: UUID
    customer_id: UUID
    customer_name: str
    kind: DeliveryKind
    name: str
    order_no: str | None
    status: DeliveryStatus
    required_languages: list[str]
    public_token: str  # system QR, `/s/{token}` (only meaningful for kind = system); never changes
    portal_url: str
    current_release_no: int | None  # null until the release tables exist (M2-B4)
    has_open_draft: bool  # false until the release tables exist (M2-B4)
    machines: list[MachineListItem]  # by sort_order, then created_at
