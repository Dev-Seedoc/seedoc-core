"""Products (API.md §3.4). HTTP only: parse, call the service function with the same name, return its schema
(`create_product_release` lives in services/releases.py). Every member manages products (`EditorCtx`, BUSINESS_RULES
§1)."""

from uuid import UUID

from fastapi import APIRouter, status

from seedoc.deps import DbSession, EditorCtx
from seedoc.schemas.common import Page
from seedoc.schemas.documents import DocumentListItem
from seedoc.schemas.products import (
    LanguageMatrixRead,
    ProductCreate,
    ProductDocumentsSet,
    ProductRead,
    ProductReleaseCreate,
    ProductReleaseDetailRead,
    ProductReleaseRead,
    ProductUpdate,
)
from seedoc.services import products as products_service
from seedoc.services import releases as releases_service

router = APIRouter(prefix="/products", tags=["products"])


@router.get("")
async def list_products(db: DbSession, ctx: EditorCtx) -> Page[ProductRead]:
    return await products_service.list_products(db, ctx)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_product(body: ProductCreate, db: DbSession, ctx: EditorCtx) -> ProductRead:
    return await products_service.create_product(db, ctx, body)


@router.get("/{product_id}")
async def get_product(product_id: UUID, db: DbSession, ctx: EditorCtx) -> ProductRead:
    return await products_service.get_product(db, ctx, product_id)


@router.patch("/{product_id}")
async def update_product(product_id: UUID, body: ProductUpdate, db: DbSession, ctx: EditorCtx) -> ProductRead:
    return await products_service.update_product(db, ctx, product_id, body)


@router.get("/{product_id}/documents")
async def list_product_documents(product_id: UUID, db: DbSession, ctx: EditorCtx) -> Page[DocumentListItem]:
    return await products_service.list_product_documents(db, ctx, product_id)


@router.put("/{product_id}/documents")
async def set_product_documents(
    product_id: UUID, body: ProductDocumentsSet, db: DbSession, ctx: EditorCtx
) -> Page[DocumentListItem]:
    return await products_service.set_product_documents(db, ctx, product_id, body)


@router.get("/{product_id}/languages")
async def get_product_language_matrix(product_id: UUID, db: DbSession, ctx: EditorCtx) -> LanguageMatrixRead:
    return await products_service.get_product_language_matrix(db, ctx, product_id)


@router.get("/{product_id}/releases")
async def list_product_releases(product_id: UUID, db: DbSession, ctx: EditorCtx) -> Page[ProductReleaseRead]:
    return await products_service.list_product_releases(db, ctx, product_id)


@router.post("/{product_id}/releases", status_code=status.HTTP_201_CREATED)
async def create_product_release(
    product_id: UUID, body: ProductReleaseCreate, db: DbSession, ctx: EditorCtx
) -> ProductReleaseRead:
    return await releases_service.create_product_release(db, ctx, product_id, body)


@router.get("/{product_id}/releases/{release_no}")
async def get_product_release(
    product_id: UUID, release_no: int, db: DbSession, ctx: EditorCtx
) -> ProductReleaseDetailRead:
    return await products_service.get_product_release(db, ctx, product_id, release_no)
