from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from database.database_app import get_session
from schemas.schemas import UserCreate, UserOut, UserUpdate
from models import User
from crud import create_user, update_user
from sqlalchemy.orm import joinedload
from uuid import UUID

router = APIRouter(prefix="/users", tags=["Пользователи"])


@router.post("/", response_model=UserOut, summary="Создать нового пользователя", description="Регистрирует нового пользователя в системе")
async def add_user(user: UserCreate, db: AsyncSession = Depends(get_session)):
    return await create_user(db, user)


@router.get("/", summary="Список пользователей", description="Возвращает список всех пользователей")
async def get_users(db: AsyncSession = Depends(get_session)):
    result = await db.execute(select(User)
            .options(
                joinedload(User.transport_company),  
                joinedload(User.tariff) 
            ))
    return result.scalars().all()


@router.get("/{user_id}", response_model=UserOut, summary="Получить пользователя по ID", description="Возвращает данные пользователя по его ID, включая связанную информацию о транспортной компании и тарифе")
async def get_user(user_id: UUID, db: AsyncSession = Depends(get_session)):
    result = await db.execute(
        select(User)
        .options(
            joinedload(User.transport_company),  
            joinedload(User.tariff) 
        )
        .where(User.id == user_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    return user

@router.patch("/{user_id}", response_model=UserOut, summary="Редактировать пользователя", description="Редактирует данные пользователя по ID")
async def update_user_endpoint( user: UserUpdate, db: AsyncSession = Depends(get_session)):
    return await update_user(db, user)


@router.delete("/{user_id}", summary="Удалить пользователя", description="Удаление пользователя по ID")
async def delete_user(user_id: UUID, db: AsyncSession = Depends(get_session)):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    
    await db.delete(user)
    await db.commit()
    return None