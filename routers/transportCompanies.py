from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from database.database_app import get_session
from models import TransportCompany
from schemas.schemas import TransportCompanyCreate, TransportCompanyOut
from sqlalchemy.orm import selectinload
from uuid import UUID

router = APIRouter(prefix="/transport-companies", tags=["Транспортные компании"])


@router.get("/", response_model=list[TransportCompanyOut], summary="Список транспортных компаний")
async def get_companies(db: AsyncSession = Depends(get_session)):
    result = await db.execute(select(TransportCompany))
    return result.scalars().all()


@router.get("/{company_id}", response_model=TransportCompanyOut, summary="Получить транспортную компанию по ID")
async def get_company(company_id: UUID, db: AsyncSession = Depends(get_session)):
    result = await db.execute(select(TransportCompany).where(TransportCompany.id == company_id))
    company = result.scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=404, detail="Транспортная компания не найдена")
    return company


@router.post("/", response_model=TransportCompanyOut, summary="Создать транспортную компанию")
async def create_company(company: TransportCompanyCreate, db: AsyncSession = Depends(get_session)):
    if hasattr(TransportCompany, "uuid_1c"):
        result = await db.execute(select(TransportCompany).where(TransportCompany.uuid_1c == company.uuid_1c))
        existing = result.scalar_one_or_none()
        if existing:
            raise HTTPException(status_code=400, detail="Компания с таким uuid_1c уже существует")

    db_company = TransportCompany(**company.dict())
    db.add(db_company)
    await db.commit()
    await db.refresh(db_company)

    result = await db.execute(
        select(TransportCompany)
        .options(selectinload(TransportCompany.legal_entity_type))
        .where(TransportCompany.id == db_company.id)
    )
    db_company = result.scalar_one()

    return db_company

@router.put("/{company_id}", response_model=TransportCompanyOut, summary="Обновить транспортную компанию")
async def update_company(company_id: UUID, company: TransportCompanyCreate, db: AsyncSession = Depends(get_session)):
    result = await db.execute(select(TransportCompany).where(TransportCompany.id == company_id))
    db_company = result.scalar_one_or_none()
    if not db_company:
        raise HTTPException(status_code=404, detail="Транспортная компания не найдена")

    for key, value in company.dict().items():
        setattr(db_company, key, value)
    db_company.changeDateTime = datetime.utcnow()
    await db.commit()
    await db.refresh(db_company)
    return db_company


@router.delete("/{company_id}", summary="Удалить транспортную компанию")
async def delete_company(company_id: UUID, db: AsyncSession = Depends(get_session)):
    result = await db.execute(select(TransportCompany).where(TransportCompany.id == company_id))
    db_company = result.scalar_one_or_none()
    if not db_company:
        raise HTTPException(status_code=404, detail="Транспортная компания не найдена")

    await db.delete(db_company)
    await db.commit()
    return {"detail": "Транспортная компания удалена"}
