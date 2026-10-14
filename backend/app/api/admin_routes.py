"""Admin endpoints: catalog CRUD, CSV import and earnings flags. Thin wrappers over pipeline.admin."""
from __future__ import annotations

from datetime import date
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.routes import get_session
from app.core.config import load_settings
from app.pipeline import admin
from app.pipeline.admin import AdminError

router = APIRouter(prefix="/api/admin")

AnnType = Literal["new_product", "partnership", "distribution", "negative_event", "other"]


class EarningsFlag(BaseModel):
    as_of: date
    status: str
    reason: str | None
    source: str
    next_earnings_date: date | None
    confirmed: bool | None
    fiscal_quarter_end: date | None
    days_to_earnings: int | None
    needs_date_update: bool


class CompanyIn(BaseModel):
    ticker: str = Field(min_length=1, max_length=16)
    name: str = Field(min_length=1, max_length=200)
    exchange: str | None = None
    sector: str | None = None
    is_demo: bool = False
    market_cap_usd_m: float | None = None
    analyst_count: int | None = None
    benchmark_ticker: str = "XLY"
    next_earnings_date: date | None = None
    earnings_date_confirmed: bool = False
    fiscal_quarter_end: date | None = None
    cashtag_exclusions: list[str] = []
    active: bool = True
    notes: str | None = None


class CompanyOut(CompanyIn):
    id: int
    product_count: int
    earnings: EarningsFlag | None = None


class ProductIn(BaseModel):
    company_id: int
    name: str = Field(min_length=1, max_length=200)
    keywords: list[str] = []
    launched_on: date | None = None
    active: bool = True


class ProductOut(ProductIn):
    id: int
    ticker: str


class AnnouncementIn(BaseModel):
    company_id: int
    product_id: int | None = None
    event_date: date
    type: AnnType
    title: str = Field(min_length=1, max_length=300)
    url: str | None = None
    notes: str | None = None


class AnnouncementAdminOut(AnnouncementIn):
    id: int
    ticker: str
    type: str


class CsvIn(BaseModel):
    csv: str
    dry_run: bool = False


class CsvError(BaseModel):
    line: int
    error: str


class ImportOut(BaseModel):
    created: int
    updated: int
    errors: list[CsvError]
    applied: bool


class CsvTemplates(BaseModel):
    companies: list[str]
    products: list[str]


def _err(e: AdminError):
    raise HTTPException(status_code=e.status, detail=str(e))


def _company(session: Session, c) -> CompanyOut:
    flags = admin.earnings_flags(session, load_settings())
    return CompanyOut.model_validate(admin.company_dict(c, flags.get(c.id)))


@router.get("/companies", response_model=list[CompanyOut])
def companies(session: Session = Depends(get_session)) -> list[CompanyOut]:
    """Companies whose earnings date needs updating come first."""
    return [CompanyOut.model_validate(c) for c in admin.list_companies(session, load_settings())]


@router.post("/companies", response_model=CompanyOut)
def create_company(body: CompanyIn, session: Session = Depends(get_session)) -> CompanyOut:
    try:
        return _company(session, admin.create_company(session, body.model_dump()))
    except AdminError as e:
        _err(e)


@router.put("/companies/{company_id}", response_model=CompanyOut)
def update_company(company_id: int, body: CompanyIn, session: Session = Depends(get_session)) -> CompanyOut:
    try:
        return _company(session, admin.update_company(session, company_id, body.model_dump()))
    except AdminError as e:
        _err(e)


@router.get("/products", response_model=list[ProductOut])
def products(company_id: int | None = None, session: Session = Depends(get_session)) -> list[ProductOut]:
    return [ProductOut.model_validate(p) for p in admin.list_products(session, company_id)]


@router.post("/products", response_model=ProductOut)
def create_product(body: ProductIn, session: Session = Depends(get_session)) -> ProductOut:
    try:
        return ProductOut.model_validate(admin.product_dict(admin.create_product(session, body.model_dump())))
    except AdminError as e:
        _err(e)


@router.put("/products/{product_id}", response_model=ProductOut)
def update_product(product_id: int, body: ProductIn, session: Session = Depends(get_session)) -> ProductOut:
    try:
        return ProductOut.model_validate(admin.product_dict(admin.update_product(session, product_id,
                                                                                 body.model_dump())))
    except AdminError as e:
        _err(e)


@router.get("/announcements", response_model=list[AnnouncementAdminOut])
def announcements(session: Session = Depends(get_session)) -> list[AnnouncementAdminOut]:
    return [AnnouncementAdminOut.model_validate(a) for a in admin.list_announcements(session)]


@router.post("/announcements", response_model=AnnouncementAdminOut)
def create_announcement(body: AnnouncementIn, session: Session = Depends(get_session)) -> AnnouncementAdminOut:
    try:
        return AnnouncementAdminOut.model_validate(admin.create_announcement(session, body.model_dump()))
    except AdminError as e:
        _err(e)


@router.put("/announcements/{ann_id}", response_model=AnnouncementAdminOut)
def update_announcement(ann_id: int, body: AnnouncementIn,
                        session: Session = Depends(get_session)) -> AnnouncementAdminOut:
    try:
        return AnnouncementAdminOut.model_validate(admin.update_announcement(session, ann_id, body.model_dump()))
    except AdminError as e:
        _err(e)


@router.delete("/announcements/{ann_id}")
def delete_announcement(ann_id: int, session: Session = Depends(get_session)) -> dict[str, Any]:
    try:
        admin.delete_announcement(session, ann_id)
    except AdminError as e:
        _err(e)
    return {"ok": True}


@router.get("/import/templates", response_model=CsvTemplates)
def templates() -> CsvTemplates:
    return CsvTemplates(companies=admin.COMPANY_CSV_COLUMNS, products=admin.PRODUCT_CSV_COLUMNS)


@router.post("/import/companies", response_model=ImportOut)
def import_companies(body: CsvIn, session: Session = Depends(get_session)) -> ImportOut:
    try:
        return ImportOut.model_validate(admin.import_companies(session, body.csv, body.dry_run))
    except AdminError as e:
        _err(e)


@router.post("/import/products", response_model=ImportOut)
def import_products(body: CsvIn, session: Session = Depends(get_session)) -> ImportOut:
    try:
        return ImportOut.model_validate(admin.import_products(session, body.csv, body.dry_run))
    except AdminError as e:
        _err(e)
