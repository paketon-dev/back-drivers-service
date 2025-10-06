from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from database.database_app import get_session
from models import Address
from schemas.schemas import AddressCreate, AddressOut

router = APIRouter(prefix="/addresses", tags=["Адреса"])


@router.get("/", response_model=list[AddressOut], summary="Список адресов")
async def get_addresses(db: AsyncSession = Depends(get_session)):
    result = await db.execute(select(Address))
    return result.scalars().all()


@router.get("/{address_id}", response_model=AddressOut, summary="Получить адрес по ID")
async def get_address(address_id: int, db: AsyncSession = Depends(get_session)):
    result = await db.execute(select(Address).where(Address.id == address_id))
    address = result.scalar_one_or_none()
    if not address:
        raise HTTPException(status_code=404, detail="Адрес не найден")
    return address


@router.post("/", response_model=AddressOut, summary="Создать адрес")
async def create_address(address: AddressCreate, db: AsyncSession = Depends(get_session)):
    db_address = Address(**address.dict())
    db.add(db_address)
    await db.commit()
    await db.refresh(db_address)
    return db_address


@router.put("/{address_id}", response_model=AddressOut, summary="Обновить адрес")
async def update_address(address_id: int, address: AddressCreate, db: AsyncSession = Depends(get_session)):
    result = await db.execute(select(Address).where(Address.id == address_id))
    db_address = result.scalar_one_or_none()
    if not db_address:
        raise HTTPException(status_code=404, detail="Адрес не найден")

    for key, value in address.dict().items():
        setattr(db_address, key, value)

    db.add(db_address)
    await db.commit()
    await db.refresh(db_address)
    return db_address


@router.delete("/{address_id}", summary="Удалить адрес")
async def delete_address(address_id: int, db: AsyncSession = Depends(get_session)):
    result = await db.execute(select(Address).where(Address.id == address_id))
    db_address = result.scalar_one_or_none()
    if not db_address:
        raise HTTPException(status_code=404, detail="Адрес не найден")

    await db.delete(db_address)
    await db.commit()
    return {"detail": "Адрес успешно удалён"}
