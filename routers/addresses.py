from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from database.database_app import get_session
from models import Address
from schemas.schemas import AddressCreate, AddressOut
from uuid import UUID

router = APIRouter(prefix="/addresses", tags=["Адреса"])


@router.get("/", response_model=list[AddressOut], summary="Список адресов")
async def get_addresses(db: AsyncSession = Depends(get_session)):
    result = await db.execute(select(Address))
    return result.scalars().all()


@router.get("/{address_id}", response_model=AddressOut, summary="Получить адрес по ID")
async def get_address(address_id: UUID, db: AsyncSession = Depends(get_session)):
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
async def update_address(address_id: UUID, address: AddressCreate, db: AsyncSession = Depends(get_session)):
    result = await db.execute(select(Address).where(Address.id == address_id))
    db_address = result.scalar_one_or_none()
    if not db_address:
        raise HTTPException(status_code=404, detail="Адрес не найден")

    for key, value in address.dict().items():
        setattr(db_address, key, value)

    if hasattr(db_address, "changeDateTime"):
        db_address.changeDateTime = datetime.utcnow()

    db.add(db_address)
    await db.commit()
    await db.refresh(db_address)
    return db_address


@router.delete("/{address_id}", summary="Удалить адрес")
async def delete_address(address_id: UUID, db: AsyncSession = Depends(get_session)):
    result = await db.execute(select(Address).where(Address.id == address_id))
    db_address = result.scalar_one_or_none()
    if not db_address:
        raise HTTPException(status_code=404, detail="Адрес не найден")

    await db.delete(db_address)
    await db.commit()
    return {"detail": "Адрес успешно удалён"}



import pandas as pd
from fastapi import UploadFile, File, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
import io
@router.post("/bulk-upload", summary="Загрузить адреса из Excel файла")
async def bulk_upload_addresses(
    file: UploadFile = File(..., description="Excel файл с колонками: address_1c, latitude, longitude"),
    db: AsyncSession = Depends(get_session)
):
    # Проверяем расширение файла
    if not file.filename.endswith(('.xlsx', '.xls')):
        raise HTTPException(status_code=400, detail="Файл должен быть в формате Excel (.xlsx или .xls)")
    
    try:
        # Читаем файл в память
        contents = await file.read()
        df = pd.read_excel(io.BytesIO(contents))
        
        # Проверяем, что есть хотя бы 3 колонки
        if df.shape[1] < 3:
            raise HTTPException(status_code=400, detail="Файл должен содержать минимум 3 колонки")
        
        # Берем только первые три колонки и переименовываем их
        df = df.iloc[:, :3]
        df.columns = ['address_1c', 'latitude', 'longitude']
        
        # Удаляем пустые строки в address_1c
        df = df.dropna(subset=['address_1c'])
        
        # Получаем существующие адреса для проверки дубликатов
        result = await db.execute(select(Address.address_1c))
        existing_addresses = {row[0] for row in result.fetchall()}
        
        addresses_to_create = []
        new_addresses_count = 0
        duplicate_addresses_count = 0
        
        for _, row in df.iterrows():
            address_1c = str(row['address_1c']).strip()
            if not address_1c:
                continue
            if address_1c in existing_addresses:
                duplicate_addresses_count += 1
                continue
            
            address_data = {
                'address_1c': address_1c,
                'latitude': float(row['latitude']) if pd.notna(row['latitude']) else None,
                'longitude': float(row['longitude']) if pd.notna(row['longitude']) else None,
            }
            addresses_to_create.append(Address(**address_data))
            existing_addresses.add(address_1c)
            new_addresses_count += 1
        
        if addresses_to_create:
            db.add_all(addresses_to_create)
            await db.commit()
            for address in addresses_to_create:
                await db.refresh(address)
        
        return {
            "message": "Обработка файла завершена",
            "total_rows_in_file": len(df),
            "new_addresses_created": new_addresses_count,
            "duplicates_skipped": duplicate_addresses_count,
            "addresses": [
                {
                    "id": str(address.id),
                    "address_1c": address.address_1c,
                    "latitude": address.latitude,
                    "longitude": address.longitude
                } for address in addresses_to_create
            ]
        }
        
    except pd.errors.EmptyDataError:
        raise HTTPException(status_code=400, detail="Файл пуст")
    except pd.errors.ParserError:
        raise HTTPException(status_code=400, detail="Ошибка при чтении файла")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Ошибка в данных: {str(e)}")
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Ошибка при обработке файла: {str(e)}")
