from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from models import RoutePlan, RoutePoint, User, Vehicle, LogEntry
from schemas.schemas import UserCreate, VehicleCreate, LogCreate
from auth import get_password_hash
from sqlalchemy.orm import selectinload

# USERS
async def create_user(db: AsyncSession, user: UserCreate):
    # Check if the username already exists
    existing_user = await db.execute(select(User).filter(User.username == user.username))
    existing_user = existing_user.scalar_one_or_none()

    if existing_user:
        # Raise an error if the username already exists
        raise HTTPException(status_code=400, detail="Username already taken")

    # If the username is available, create the new user
    db_user = User(    username=user.username,
    hashed_password=get_password_hash(user.password),
    first_name=user.first_name,
    last_name=user.last_name,
    middle_name=user.middle_name,
    rate=user.rate,
    is_active=True )
    db.add(db_user)
    await db.commit()
    await db.refresh(db_user)
    return db_user


# VEHICLES
async def create_vehicle(db: AsyncSession, user_id: int, vehicle: VehicleCreate):
    db_vehicle = Vehicle(**vehicle.dict(), owner_id=user_id)
    db.add(db_vehicle)
    await db.commit()
    await db.refresh(db_vehicle)
    return db_vehicle


# LOGS
from zoneinfo import ZoneInfo
from datetime import datetime

async def create_log(db: AsyncSession, vehicle_id: int, log: LogCreate):
    # Получаем текущее время с учётом часового пояса Барнаула
    barnaul_time = datetime.now(ZoneInfo("Asia/Barnaul"))
    
    # Записываем лог с учётом времени в Барнауле
    db_log = LogEntry(vehicle_id=vehicle_id, timestamp=barnaul_time, **log.dict())
    
    # Добавляем и сохраняем лог
    db.add(db_log)
    await db.commit()
    await db.refresh(db_log)
    return db_log


async def get_vehicle_logs(db: AsyncSession, vehicle_id: int):
    result = await db.execute(select(LogEntry).where(LogEntry.vehicle_id == vehicle_id))
    return result.scalars().all()




# Создать маршрут для автомобиля
async def create_route_plan(db: AsyncSession, vehicle_id: int, date: datetime, notes: str = None):
    plan = RoutePlan(vehicle_id=vehicle_id, date=date, notes=notes)
    db.add(plan)
    await db.commit()
    await db.refresh(plan)
    return plan

# Добавить точку маршрута
async def add_route_point(
    db: AsyncSession,
    route_plan_id: int,
    doc: str,
    payment: float,
    counterparty: str,
    address: str,
    note: str = None,
    order: int | None = None
):
    # Получаем все существующие точки маршрута для этого маршрута
    result = await db.execute(
        select(RoutePoint)
        .where(RoutePoint.route_plan_id == route_plan_id)
        .order_by(RoutePoint.order.asc())
    )
    existing_points = result.scalars().all()

    if order is None:
        # Если order не передан, ставим следующий после максимального
        order = max((p.order for p in existing_points), default=0) + 1
    else:
        # Если order передан, проверяем конфликты и сдвигаем остальные
        for p in existing_points:
            if p.order >= order:
                p.order += 1
                db.add(p)  # помечаем для обновления

    # Создаём новую точку маршрута
    point = RoutePoint(
        route_plan_id=route_plan_id,
        doc=doc,
        payment=payment,
        counterparty=counterparty,
        address=address,
        order=order,
        arrival_time=None,
        departure_time=None,
        duration_minutes=None,
        note=note
    )

    db.add(point)
    await db.commit()
    await db.refresh(point)
    return point

# Получить маршрут с точками для автомобиля
async def get_route_plan(db: AsyncSession, vehicle_id: int, date: datetime):
    result = await db.execute(
        select(RoutePlan).where(RoutePlan.vehicle_id == vehicle_id, RoutePlan.date == date).options(selectinload(RoutePlan.points))
    )
    return result.scalars().first()
