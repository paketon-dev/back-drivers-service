from io import BytesIO
import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from database.database_app import get_session
from routers.auth import get_current_user
from models import Address, RoutePointStatusLog, RouteStatusEnum, Vehicle, RoutePlan, RoutePoint, User
from crud import create_route_plan, add_route_point
from datetime import date, datetime
from schemas.schemas import PointStatusUpdate
from sqlalchemy import func, or_
import bcrypt
from sqlalchemy.orm import selectinload

router = APIRouter(prefix="/routes", tags=["Маршруты"])

# Асинхронная функция для получения первой машины пользователя
async def get_user_vehicle(db: AsyncSession, user_id: int) -> Vehicle | None:
    result = await db.execute(select(Vehicle).where(Vehicle.owner_id == user_id))
    return result.scalars().first()



# Создать маршрут на день для автомобиля пользователя
@router.post("/", summary="Создать маршрут на день")
async def create_route(
    date: date = Query(..., description="Дата маршрута"),
    notes: str | None = None,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    vehicle = await get_user_vehicle(db, current_user.id)
    if not vehicle:
        raise HTTPException(status_code=403, detail="У вас нет автомобилей для создания маршрута")
    
    return await create_route_plan(db, vehicle.id, date, notes)

from sqlalchemy.orm import selectinload


@router.get("/logsAll")
async def get_route_point_logs(
    db: AsyncSession = Depends(get_session)
):
    result = await db.execute(
        select(RoutePoint)
        .options(selectinload(RoutePoint.route_plan).selectinload(RoutePlan.vehicle))
    )
    points = result.scalars().all()

    if not points:
        raise HTTPException(status_code=404, detail="Точка маршрута не найдена")

    result = await db.execute(
        select(RoutePointStatusLog)
        .order_by(RoutePointStatusLog.timestamp)
    )
    logs = result.scalars().all()

    return {
        "points": [
            {
                "id": p.id,
                "route_plan_id": p.route_plan_id,
                "order": p.order,
                "doc": p.doc,
                "payment": p.payment,
                "counterparty": p.counterparty,
                "address": p.address,
                "arrival_time": p.arrival_time,
                "departure_time": p.departure_time,
                "duration_minutes": p.duration_minutes,
                "note": p.note,
                "status": p.status,
            }
            for p in points
        ],
        "logs": [
            {
                "id": l.id,
                "point_id": l.point_id,
                "status": l.status,
                "timestamp": l.timestamp
            }
            for l in logs
        ]
    }





# Добавить точку маршрута
@router.post("/{route_id}/points", summary="Добавить точку маршрута")
async def add_point(
    route_id: int,
    doc: str,
    payment: float,
    counterparty: str,
    address: str,
    note: str | None = None,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(RoutePlan)
        .options(selectinload(RoutePlan.vehicle))
        .where(RoutePlan.id == route_id)
    )
    route = result.scalars().first()
    
    if not route or route.vehicle.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Нет доступа к этому маршруту")
    
    return await add_route_point(db, route_id, doc, payment, counterparty, address, note)

async def get_or_create_today_route(db: AsyncSession, user_id: int) -> RoutePlan:
    result = await db.execute(
        select(RoutePlan)
        .join(RoutePlan.vehicle)
        .where(RoutePlan.date == date.today(), RoutePlan.vehicle.has(owner_id=user_id))
        .options(selectinload(RoutePlan.vehicle))
    )
    route = result.scalars().first()

    if route:
        return route
    
    result = await db.execute(select(Vehicle).where(Vehicle.owner_id == user_id))
    vehicle = result.scalars().first()
    if not vehicle:
        raise HTTPException(status_code=403, detail="У вас нет автомобилей для создания маршрута")
    
    return await create_route_plan(db, vehicle.id, date.today(), notes="Автоматически созданный маршрут")


@router.post("/points", summary="Добавить точку маршрута для сегодняшнего маршрута")
async def add_point_today(
    doc: str,
    payment: float,
    counterparty: str,
    address: str,
    order: int | None = None, 
    note: str | None = None,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    route = await get_or_create_today_route(db, current_user.id)
    
    if not route:
        raise HTTPException(status_code=404, detail="Маршрут на сегодня не найден для вашего автомобиля")
    
    return await add_route_point(
        db,
        route_plan_id=route.id,
        doc=doc,
        payment=payment,
        counterparty=counterparty,
        address=address,
        note=note,
        order=order
    )



@router.post("/users/{user_id}/points", summary="Создать точку маршрута для пользователя по ID")
async def create_point_for_user(
    user_id: int,
    doc: str,
    payment: float,
    counterparty: str,
    address: str,
    note: str | None = None,
    db: AsyncSession = Depends(get_session)
):
    result = await db.execute(select(User).where(User.id == user_id).options(selectinload(User.vehicles)))
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    vehicle = user.vehicles[0] if user.vehicles else None
    if not vehicle:
        raise HTTPException(status_code=404, detail="У пользователя нет автомобилей")

    result = await db.execute(
        select(RoutePlan)
        .where(RoutePlan.vehicle_id == vehicle.id)
        .where(func.date(RoutePlan.date) == datetime.utcnow().date())
    )
    route = result.scalars().first()

    if not route:
        route = await create_route_plan(db, vehicle.id, datetime.utcnow().date(), notes="Автоматически созданный маршрут")

    point = await add_route_point(
        db,
        route_plan_id=route.id,
        doc=doc,
        payment=payment,
        counterparty=counterparty,
        address=address,
        note=note
    )

    return point



@router.get("/filter", summary="Получить все маршруты за период")
async def get_all_routes(
    db: AsyncSession = Depends(get_session),
    start_date: date | None = Query(None, description="Дата начала фильтрации"),
    end_date: date | None = Query(None, description="Дата окончания фильтрации")
):
    query = select(RoutePlan).options(
        selectinload(RoutePlan.vehicle)
        .selectinload(Vehicle.owner),
        selectinload(RoutePlan.points)
        .selectinload(RoutePoint.address) 
    )

    if start_date:
        query = query.where(RoutePlan.date >= start_date)
    if end_date:
        query = query.where(RoutePlan.date <= end_date)

    result = await db.execute(query)
    routes = result.scalars().all()

    if not routes:
        raise HTTPException(status_code=404, detail="Маршруты не найдены")

    return routes


@router.get("/all", summary="Получить все маршруты")
async def get_all_routes(
    db: AsyncSession = Depends(get_session),
):
    query = select(RoutePlan).options(
        selectinload(RoutePlan.vehicle)
        .selectinload(Vehicle.owner),
        selectinload(RoutePlan.points)
    )

    result = await db.execute(query)
    routes = result.scalars().all()

    if not routes:
        raise HTTPException(status_code=404, detail="Маршруты не найдены")

    return routes

@router.get("/stats", summary="Получить статистику маршрутов и точек")
async def get_routes_stats(db: AsyncSession = Depends(get_session)):
    result_routes = await db.execute(select(func.count(RoutePlan.id)))
    total_routes = result_routes.scalar() or 0

    result_points = await db.execute(select(func.count(RoutePoint.id)))
    total_points = result_points.scalar() or 0

    return {
        "total_routes": total_routes,
        "total_points": total_points
    }

@router.get("/user/{user_id}", summary="Получить все маршруты пользователя по ID")
async def get_user_routes(
    user_id: int,
    db: AsyncSession = Depends(get_session)
):
    result_user = await db.execute(select(User).where(User.id == user_id))
    user = result_user.scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    query = (
        select(RoutePlan)
        .join(RoutePlan.vehicle)
        .where(Vehicle.owner_id == user_id)
        .options(
            selectinload(RoutePlan.vehicle).selectinload(Vehicle.owner),  
            selectinload(RoutePlan.points) 
        )
    )

    result_routes = await db.execute(query)
    routes = result_routes.scalars().all()

    if not routes:
        raise HTTPException(status_code=404, detail="Маршруты пользователя не найдены")

    return routes


@router.get("/user/{user_id}/summary", summary="Получить маршруты пользователя и количество точек")
async def get_user_routes_summary(
    user_id: int,
    db: AsyncSession = Depends(get_session)
):
    result_user = await db.execute(select(User).where(User.id == user_id))
    user = result_user.scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    query_routes = (
        select(RoutePlan)
        .join(RoutePlan.vehicle)
        .where(Vehicle.owner_id == user_id)
        .options(
            selectinload(RoutePlan.vehicle).selectinload(Vehicle.owner) 
        )
    )
    result_routes = await db.execute(query_routes)
    routes = result_routes.scalars().all()

    if not routes:
        raise HTTPException(status_code=404, detail="Маршруты пользователя не найдены")

    route_summaries = []
    for route in routes:
        result_count = await db.execute(
            select(func.count(RoutePoint.id))
            .where(RoutePoint.route_plan_id == route.id)
        )
        point_count = result_count.scalar() or 0
        route_summaries.append({
            "route_id": route.id,
            "date": route.date,
            "status": route.status,
            "vehicle": {
                "id": route.vehicle.id,
                "plate_number": route.vehicle.plate_number,
                "model": route.vehicle.model,
                "owner": {
                    "id": route.vehicle.owner.id,
                    "first_name": route.vehicle.owner.first_name,
                    "last_name": route.vehicle.owner.last_name,
                    "middle_name": route.vehicle.owner.middle_name
                }
            },
            "points_count": point_count
        })

    return route_summaries

from sqlalchemy import select
from sqlalchemy.orm import selectinload

@router.post("/points/{point_id}/move", summary="Переместить точку маршрута")
async def move_route_point(
    point_id: int,
    new_order: int,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(RoutePoint)
        .options(selectinload(RoutePoint.route_plan).selectinload(RoutePlan.vehicle))
        .where(RoutePoint.id == point_id)
    )
    point = result.scalars().first()
    if not point:
        raise HTTPException(status_code=404, detail="Точка маршрута не найдена")
    
    route = point.route_plan
    if not route or route.vehicle.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Нет доступа к этому маршруту")

    old_order = point.order
    if new_order == old_order:
        return point 

    result = await db.execute(
        select(RoutePoint)
        .where(RoutePoint.route_plan_id == route.id)
        .order_by(RoutePoint.order)
    )
    points = result.scalars().all()

    if new_order < old_order:
        for p in points:
            if new_order <= p.order < old_order:
                p.order += 1
    else:
        for p in points:
            if old_order < p.order <= new_order:
                p.order -= 1

    point.order = new_order
    db.add_all(points)
    await db.commit()
    await db.refresh(point)
    return point



# Получить маршрут текущего пользователя на сегодня
@router.get("/today", summary="Получить маршрут текущего пользователя на сегодня")
async def get_today_route(
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(RoutePlan)
        .join(RoutePlan.vehicle)
        .where(RoutePlan.date == date.today(), RoutePlan.vehicle.has(owner_id=current_user.id))
        .options(selectinload(RoutePlan.points), selectinload(RoutePlan.vehicle))
    )
    route = result.scalars().first()
    
    if not route:
        raise HTTPException(status_code=404, detail="Маршрут на сегодня не найден")
    
    return route

# Получить маршрут по id (динамический)
@router.get("/{route_id}", summary="Получить маршрут по ID с точками и водителем")
async def get_route_by_id(
    route_id: int,
    db: AsyncSession = Depends(get_session)
):
    result = await db.execute(
        select(RoutePlan)
        .options(
            selectinload(RoutePlan.vehicle).selectinload(Vehicle.owner), 
            selectinload(RoutePlan.points)
        )
        .where(RoutePlan.id == route_id)
    )
    route = result.scalars().first()

    return route


from models import RoutePointStatusEnum

@router.post("/points/{point_id}/status")
async def update_route_point_status(
    point_id: int,
    data: PointStatusUpdate,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(RoutePoint)
        .options(selectinload(RoutePoint.route_plan).selectinload(RoutePlan.vehicle))
        .where(RoutePoint.id == point_id)
    )
    point = result.scalars().first()
    if not point:
        raise HTTPException(status_code=404, detail="Точка маршрута не найдена")

    if point.route_plan.vehicle.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Нет доступа к этому маршруту")

    now = data.timestamp or datetime.utcnow()

    point.status = data.new_status
    
    if data.new_status == RoutePointStatusEnum.arrived:
        point.arrival_time = point.arrival_time or now
    elif data.new_status == RoutePointStatusEnum.completed:
        if not point.arrival_time:
            point.arrival_time = now
        point.departure_time = now

    log = RoutePointStatusLog(
        point_id=point.id,
        status=data.new_status,
        timestamp=now,
        latitude=data.lat,
        longitude=data.lng
    )
    db.add(log)

    db.add(point)
    await db.commit()
    await db.refresh(point)
    return point



@router.post("/points/{point_id}/statussss")
async def update_route_point_status(
    point_id: int,
    data: PointStatusUpdate,
    db: AsyncSession = Depends(get_session)
):
    result = await db.execute(
        select(RoutePoint)
        .options(selectinload(RoutePoint.route_plan).selectinload(RoutePlan.vehicle))
        .where(RoutePoint.id == point_id)
    )
    point = result.scalars().first()
    if not point:
        raise HTTPException(status_code=404, detail="Точка маршрута не найдена")

    now = data.timestamp or datetime.utcnow()

    point.status = data.new_status

    if data.new_status == RoutePointStatusEnum.arrived:
        point.arrival_time = point.arrival_time or now
    elif data.new_status == RoutePointStatusEnum.completed:
        if not point.arrival_time:
            point.arrival_time = now
        point.departure_time = now

    log = RoutePointStatusLog(
        point_id=point.id,
        status=data.new_status,
        timestamp=now,
        latitude=data.lat,
        longitude=data.lng
    )
    db.add(log)

    db.add(point)
    await db.commit()
    await db.refresh(point)
    return point


@router.get("/points/{point_id}/logs", summary="Получить историю статусов точки маршрута")
async def get_route_point_logs(
    point_id: int,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(RoutePoint)
        .options(selectinload(RoutePoint.route_plan).selectinload(RoutePlan.vehicle))
        .where(RoutePoint.id == point_id)
    )
    point = result.scalars().first()
    if not point:
        raise HTTPException(status_code=404, detail="Точка маршрута не найдена")
    if point.route_plan.vehicle.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Нет доступа к этой точке")

    result = await db.execute(
        select(RoutePointStatusLog)
        .where(RoutePointStatusLog.point_id == point_id)
        .order_by(RoutePointStatusLog.timestamp)
    )
    logs = result.scalars().all()
    return logs



@router.get("/points/{point_id}/logsAdmin")
async def get_route_point_logs(
    point_id: int,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(RoutePoint)
        .options(selectinload(RoutePoint.route_plan).selectinload(RoutePlan.vehicle))
        .where(RoutePoint.id == point_id)
    )
    point = result.scalars().first()
    if not point:
        raise HTTPException(status_code=404, detail="Точка маршрута не найдена")

    result = await db.execute(
        select(RoutePointStatusLog)
        .where(RoutePointStatusLog.point_id == point_id)
        .order_by(RoutePointStatusLog.timestamp)
    )
    logs = result.scalars().all()
    return logs







def safe_str(value):
    if pd.isna(value):
        return ""
    return str(value).strip()


async def find_or_create_user(db: AsyncSession, first_name: str | None, last_name: str | None, middle_name: str | None) -> int:
    filters = []
    if first_name:
        filters.append(User.first_name.ilike(first_name))
    if last_name:
        filters.append(User.last_name.ilike(last_name))
    if middle_name:
        filters.append(User.middle_name.ilike(middle_name))

    result = await db.execute(select(User).filter(or_(*filters)))
    user = result.scalars().first()

    if not user:
        username = "".join(filter(None, [
            last_name or "",
            first_name[0] if first_name else "",
            middle_name[0] if middle_name else ""
        ])) or "driver"

        password = "".join([last_name or "", first_name[0] if first_name else "", middle_name[0] if middle_name else ""])
        hashed_password = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        
        user = User(
            username=username,
            hashed_password=hashed_password,
            first_name=first_name or "",
            last_name=last_name or "",
            middle_name=middle_name,
            is_active=True
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

    return user.id

async def get_or_create_vehicle(db: AsyncSession, user_id: int):
    result = await db.execute(select(Vehicle).filter(Vehicle.owner_id == user_id))
    vehicle = result.scalars().first()

    if not vehicle:
        vehicle = Vehicle(
            plate_number=f"AUTO_{user_id}",
            model="Неизвестно",
            owner_id=user_id
        )
        db.add(vehicle)
        await db.commit()
        await db.refresh(vehicle)

    return vehicle

# Получение или создание маршрута для указанной даты
async def get_or_create_route_for_date(db: AsyncSession, user_id: int, route_date: datetime) -> RoutePlan:
    vehicle = await get_or_create_vehicle(db, user_id)
    
    result = await db.execute(
        select(RoutePlan).filter(
            RoutePlan.vehicle_id == vehicle.id,
            func.date(RoutePlan.date) == route_date.date()
        )
    )
    route = result.scalars().first()

    if not route:
        route = RoutePlan(
            vehicle_id=vehicle.id,
            date=route_date,
            status=RouteStatusEnum.planned
        )
        db.add(route)
        await db.commit()
        await db.refresh(route)

    return route




from fastapi import Form, File, UploadFile, HTTPException, Depends
from datetime import datetime

import httpx
from fastapi import HTTPException
from pydantic import BaseModel
from fastapi import HTTPException, UploadFile, File, Form, Depends
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime
import pandas as pd
from io import BytesIO
import httpx


# Модель ответа геокодера
class GeocodeResponse:
    def __init__(self, lat: float, lng: float):
        self.lat = lat
        self.lng = lng

# Асинхронная функция получения координат по адресу
async def get_coordinates_by_address(address: str) -> GeocodeResponse | None:
    url = f"https://nominatim.openstreetmap.org/search?format=json&q={address}"
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers={"User-Agent": "YourAppName (contact@yourapp.com)"})
            response.raise_for_status()
            data = response.json()
            if not data:
                return None
            return GeocodeResponse(lat=float(data[0]["lat"]), lng=float(data[0]["lon"]))
        except Exception:
            return None

# Парсинг Excel
def parse_excel(file: UploadFile) -> pd.DataFrame:
    contents = file.file.read()
    df = pd.read_excel(BytesIO(contents))
    return df


from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
import httpx

# Геокодирование 
async def geocode(address: str):
    url = f"https://nominatim.openstreetmap.org/search?format=json&q={address}"

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers={"User-Agent": "YourAppName (contact@yourapp.com)"})
            response.raise_for_status()  
            data = response.json()
            
            if not data:
                raise HTTPException(status_code=404, detail="Address not found")
            
            lat = float(data[0]["lat"])
            lon = float(data[0]["lon"])
            
            return lat, lon
        
        except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=e.response.status_code, detail=f"HTTP error occurred: {e}")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")

# Получение или создание адреса
async def get_or_create_address(db: AsyncSession, address_text: str) -> Address:
    result = await db.execute(select(Address).filter(Address.address_1c == address_text))
    address = result.scalars().first()
    if address:
        return address
    lat, lon = await geocode(address_text)
    new_address = Address(
        address_1c=address_text,
        latitude=lat,
        longitude=lon
    )

    db.add(new_address)
    await db.flush() 
    return new_address

@router.post("/upload_excel", summary="Загрузить Excel файл с точками маршрута")
async def upload_excel(
    route_date: datetime = Form(...), 
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_session)
):
    df = parse_excel(file)
    df.columns = df.columns.str.strip()

    for index, row in df.iterrows():
        driver_name = str(row.get("Водитель", "")).strip()
        if not driver_name:
            raise HTTPException(status_code=400, detail=f"Пустое имя водителя в строке {index+1}")

        parts = driver_name.split()
        last_name = parts[0] if len(parts) > 0 else None
        first_name = parts[1] if len(parts) > 1 else None
        middle_name = parts[2] if len(parts) > 2 else None

        driver_id = await find_or_create_user(db, first_name, last_name, middle_name)
        await get_or_create_vehicle(db, driver_id)

        order_value = row.get("Порядок", index + 1)
        route = await get_or_create_route_for_date(db, driver_id, route_date)
        route_id = route.id

        doc_value = safe_str(row.get("Документ"))
        address_value = safe_str(row.get("Торговая точка"))

        coords = await get_coordinates_by_address(address_value)
        latitude = coords.lat if coords else None
        longitude = coords.lng if coords else None

        existing_point_res = await db.execute(
            select(RoutePoint).filter(RoutePoint.doc == doc_value, RoutePoint.route_plan_id == route_id)
        )

        address_obj = await get_or_create_address(db, address_value)

        existing_point = existing_point_res.scalars().first()

        if existing_point:
            existing_point.payment = row.get("Сумма документа", 0) or 0
            existing_point.counterparty = safe_str(row.get("Контрагент"))
            existing_point.address = address_obj
            existing_point.order = order_value
            existing_point.note = safe_str(row.get("Комментарий"))
            
            existing_point.latitude = latitude if latitude else address_obj.latitude
            existing_point.longitude = longitude if longitude else address_obj.longitude

            db.add(existing_point)
        else:
            await add_route_point(
                db,
                route_plan_id=route_id,
                doc=doc_value,
                payment=row.get("Сумма документа", 0) or 0,
                counterparty=safe_str(row.get("Контрагент")),
                address_obj=address_obj,
                order=order_value,
                note=safe_str(row.get("Комментарий")),
            )

    excel_docs = df["Документ"].apply(str).unique()
    existing_points_res = await db.execute(
        select(RoutePoint).filter(
            RoutePoint.route_plan_id == route_id,
            RoutePoint.doc.notin_(excel_docs)
        )
    )
    points_to_delete = existing_points_res.scalars().all()
    for point in points_to_delete:
        db.delete(point)

    await db.commit()

    return {"detail": f"Файл успешно обработан, загружено {len(df)} строк"}
