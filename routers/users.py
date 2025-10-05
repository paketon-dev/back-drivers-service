from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from database.database_app import get_session
from routers.auth import get_current_user
from schemas.schemas import UserCreate, UserOut
from models import User
from crud import create_user

router = APIRouter(prefix="/users", tags=["Пользователи"])


@router.post("/", response_model=UserOut, summary="Создать нового пользователя", description="Регистрирует нового пользователя в системе")
async def add_user(user: UserCreate, db: AsyncSession = Depends(get_session)):
    return await create_user(db, user)


@router.get("/", summary="Список пользователей", description="Возвращает список всех пользователей")
async def get_users(db: AsyncSession = Depends(get_session)):
    result = await db.execute(select(User))
    return result.scalars().all()


@router.get("/{user_id}", response_model=UserOut, summary="Получить пользователя по ID", description="Возвращает данные пользователя по его ID")
async def get_user(user_id: int, db: AsyncSession = Depends(get_session), current_user: User = Depends(get_current_user)):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    return user
