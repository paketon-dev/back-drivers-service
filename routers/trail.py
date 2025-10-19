from io import BytesIO
import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from database.database_app import get_session
from routers.auth import get_current_user
from models import Address, Loading, LoadingPlace, LoadingStatusLog, RoutePointStatusLog, RouteStatusEnum, Store, Vehicle, RoutePlan, RoutePoint, User
from crud import create_route_plan, add_route_point
from datetime import date, datetime
from schemas.schemas import PointStatusUpdate, RouteDateUpdate
from sqlalchemy import func, or_
import bcrypt
from sqlalchemy.orm import selectinload
from fastapi import Body
from models import RoutePointStatusEnum
from uuid import UUID

router = APIRouter(prefix="/routes", tags=["Маршруты"])


async def get_user_vehicle(db: AsyncSession, user_id: UUID) -> Vehicle | None:
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
    route_id: UUID,
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

async def get_or_create_today_route(db: AsyncSession, user_id: UUID) -> RoutePlan:
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
    order: UUID | None = None, 
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


@router.patch("/{route_id}/datetime", summary="Установить start_datetime или end_datetime маршрута")
async def update_route_datetime(
    route_id: UUID,
    data: RouteDateUpdate = Body(...),
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(RoutePlan)
        .options(selectinload(RoutePlan.vehicle))
        .where(RoutePlan.id == route_id)
    )
    route = result.scalars().first()
    if not route:
        raise HTTPException(status_code=404, detail="Маршрут не найден")
    
    if route.vehicle.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Нет доступа к этому маршруту")
    
    updated = False
    if data.start_datetime:
        route.start_datetime = data.start_datetime
        updated = True
    if data.end_datetime:
        route.end_datetime = data.end_datetime
        updated = True
    
    if updated:
        route.changeDateTime = datetime.utcnow()
        db.add(route)
        await db.commit()
        await db.refresh(route)
    
    return route


@router.post("/users/{user_id}/points", summary="Создать точку маршрута для пользователя по ID")
async def create_point_for_user(
    user_id: UUID,
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
    user_id: UUID,
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
    user_id: UUID,
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
    point_id: UUID,
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







@router.get("/{route_id}/timeline", summary="Получить все точки и погрузки маршрута с логами по времени")
async def get_route_timeline(route_id: UUID, db: AsyncSession = Depends(get_session)):
    # Загружаем маршрут с точками и погрузками + логи
    result = await db.execute(
        select(RoutePlan)
        .where(RoutePlan.id == route_id)
        .options(
            # Загружаем точки маршрута с адресом и магазином
            selectinload(RoutePlan.points)
                .selectinload(RoutePoint.address),
            selectinload(RoutePlan.points)
                .selectinload(RoutePoint.store)
                .selectinload(Store.address),
            selectinload(RoutePlan.points)
                .selectinload(RoutePoint.status_logs),
            
            # Загружаем погрузки с местом загрузки и логами
            selectinload(RoutePlan.loadings)
                .selectinload(Loading.loading_place)
                .selectinload(LoadingPlace.address),
            selectinload(RoutePlan.loadings)
                .selectinload(Loading.status_logs)
        )
    )

    route = result.scalars().first()
    if not route:
        raise HTTPException(status_code=404, detail="Маршрут не найден")

    timeline = []

    # Обрабатываем точки маршрута
    for point in route.points:
        for log in point.status_logs:
            timeline.append({
                "type": "route_point",
                "id": point.id,
                "name": point.store.name if point.store else (point.address.address_1c if point.address else None),
                "status": log.status,
                "latitude": log.latitude,
                "longitude": log.longitude,
                "timestamp": log.timestamp,
                "note": log.note
            })

    # Обрабатываем погрузки
    for loading in route.loadings:
        loading_place_name = loading.loading_place.name if loading.loading_place else None
        for log in loading.status_logs:
            timeline.append({
                "type": "loading",
                "id": loading.id,
                "name": loading_place_name,
                "status": log.status,
                "latitude": log.latitude,
                "longitude": log.longitude,
                "timestamp": log.timestamp,
                "note": log.note
            })

    # Сортировка по времени
    timeline.sort(key=lambda x: x["timestamp"])

    return timeline





import math
from datetime import date, datetime
from fastapi.responses import JSONResponse
from sqlalchemy.inspection import inspect
from sqlalchemy.orm.state import InstanceState
from uuid import UUID

import math
from datetime import date, datetime
from uuid import UUID
from sqlalchemy.inspection import inspect
from sqlalchemy.orm.state import InstanceState

import math
from datetime import date, datetime
from uuid import UUID
from sqlalchemy.inspection import inspect
from sqlalchemy.orm.state import InstanceState

def serialize_model(obj):
    if obj is None:
        return None
    if isinstance(obj, list):
        return [serialize_model(o) for o in obj]
    if isinstance(obj, float):
        return None if math.isnan(obj) or math.isinf(obj) else obj
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    if isinstance(obj, UUID):  
        return str(obj)  # Ensure UUIDs are converted to string
    
    # Handle any object with relationships
    if hasattr(obj, '__table__'):  # Check if it's a SQLAlchemy model
        data = {c.key: serialize_model(getattr(obj, c.key)) for c in obj.__table__.columns}

        state: InstanceState = getattr(obj, '_sa_instance_state', None)
        if state:
            for rel in inspect(obj.__class__).relationships:
                if rel.key in state.dict:
                    # Serialize related objects
                    data[rel.key] = serialize_model(getattr(obj, rel.key))

        return data
    
    return obj





@router.get("/today", summary="Get today's route with loadings")
async def get_today_route(
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    # Запрашиваем маршрут для текущего дня
    result = await db.execute(
        select(RoutePlan)
        .join(RoutePlan.vehicle)
        .where(RoutePlan.date == date.today(), RoutePlan.vehicle.has(owner_id=current_user.id))
        .options(
            selectinload(RoutePlan.points).selectinload(RoutePoint.address),
            selectinload(RoutePlan.vehicle)
        )
    )
    route = result.scalars().first()

    if not route:
        raise HTTPException(status_code=404, detail="Route not found")

    # Запрашиваем погрузки для найденного маршрута
    result_loadings = await db.execute(
        select(Loading)
        .join(Loading.route_plan)
        .where(Loading.route_plan_id == route.id)
        .options(selectinload(Loading.loading_place).selectinload(LoadingPlace.address))
    )

    loadings = result_loadings.scalars().all()

    # Подготовим данные о погрузках
    loadings_data = []
    for loading in loadings:
        # Manually serialize the loading
        loading_data = {
            "id": loading.id,
            "doc_number": loading.doc_number,  # Исправлено на doc_number
            "loading_point": True,
            "start_time": loading.start_time,
            "status": loading.status,
            "route_plan_id": loading.route_plan_id,
            "loading_place": {
                "id": loading.loading_place.id,
                "address":  loading.loading_place.address.address_1c if loading.loading_place and loading.loading_place.address else None,
                "name": loading.loading_place.name,
                "phone": loading.loading_place.phone,
                "work_hours": loading.loading_place.work_hours,
                "note": loading.loading_place.note, 
            }
        }
        loadings_data.append(loading_data)

    route_data = {
        "id": route.id,
        "start_datetime": route.start_datetime,
        "end_datetime": route.end_datetime,
        
        "vehicle_id": route.vehicle.id,
        "date": route.date.isoformat(), 
        "vehicle": {
            "id": route.vehicle.id,
        },
        "points": route.points,
    }

    # Add loadings to route data
    route_data['loadings'] = loadings_data

    return route_data


@router.get("/{route_id}", summary="Получить маршрут по ID с точками и водителем")
async def get_route_by_id(
    route_id: UUID,
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




# @router.post("/points/{point_id}/status")
# async def update_route_point_status(
#     point_id: int,
#     data: PointStatusUpdate,
#     db: AsyncSession = Depends(get_session),
#     current_user: User = Depends(get_current_user)
# ):
#     result = await db.execute(
#         select(RoutePoint)
#         .options(selectinload(RoutePoint.route_plan).selectinload(RoutePlan.vehicle))
#         .where(RoutePoint.id == point_id)
#     )
#     point = result.scalars().first()
#     if not point:
#         raise HTTPException(status_code=404, detail="Точка маршрута не найдена")

#     if point.route_plan.vehicle.owner_id != current_user.id:
#         raise HTTPException(status_code=403, detail="Нет доступа к этому маршруту")

#     now = data.timestamp or datetime.utcnow()

#     point.status = data.new_status
    
#     if data.new_status == RoutePointStatusEnum.arrived:
#         point.arrival_time = point.arrival_time or now
#     elif data.new_status == RoutePointStatusEnum.completed:
#         if not point.arrival_time:
#             point.arrival_time = now
#         point.departure_time = now

#     log = RoutePointStatusLog(
#         point_id=point.id,
#         status=data.new_status,
#         timestamp=now,
#         latitude=data.lat,
#         longitude=data.lng
#     )
#     db.add(log)

#     db.add(point)
#     await db.commit()
#     await db.refresh(point)
#     return point


@router.post("/points/{point_id}/status")
async def update_route_point_status(
    point_id: UUID,
    data: PointStatusUpdate,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    now = data.timestamp or datetime.utcnow()
    latitude = data.lat
    longitude = data.lng
    status = data.new_status

    # --- Ищем точку маршрута ---
    result = await db.execute(
        select(RoutePoint)
        .options(selectinload(RoutePoint.route_plan).selectinload(RoutePlan.vehicle))
        .where(RoutePoint.id == point_id)
    )
    point = result.scalars().first()

    if point:
        if point.route_plan.vehicle.owner_id != current_user.id:
            raise HTTPException(status_code=403, detail="Нет доступа к этому маршруту")

        point.status = status

        if status == RoutePointStatusEnum.arrived:
            point.arrival_time = point.arrival_time or now
        elif status == RoutePointStatusEnum.completed:
            if not point.arrival_time:
                point.arrival_time = now
            point.departure_time = now

        log = RoutePointStatusLog(
            point_id=point.id,
            status=status,
            timestamp=now,
            latitude=latitude,
            longitude=longitude
        )

        db.add_all([point, log])
        await db.commit()
        await db.refresh(point)
        return point

    # --- Если точки маршрута нет, ищем загрузку ---
    result = await db.execute(
        select(Loading)
        .options(selectinload(Loading.route_plan).selectinload(RoutePlan.vehicle))
        .where(Loading.id == point_id)
    )
    loading = result.scalars().first()

    if not loading:
        raise HTTPException(status_code=404, detail="Точка маршрута или загрузка не найдена")

    if loading.route_plan.vehicle.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Нет доступа к этому маршруту")

    loading.status = status
    loading.start_time = now
    log = LoadingStatusLog(
        loading_id=loading.id,
        status=status,
        timestamp=now,
        latitude=latitude,
        longitude=longitude
    )

    db.add_all([loading, log])
    await db.commit()
    await db.refresh(loading)
    return loading



@router.post("/points/{point_id}/statussss")
async def update_route_point_status(
    point_id: UUID,
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
    point_id: UUID,
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
    point_id: UUID,
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

async def get_or_create_vehicle(db: AsyncSession, user_id: UUID):
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
async def get_or_create_route_for_date(db: AsyncSession, user_id: UUID, route_date: datetime) -> RoutePlan:
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
                lat = float(0)
                lon = float(0)
            
                return lat, lon
            
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

    return {"detail": f"Файл успешно обработан, загружено {len(df)} строк"}\




@router.post("/upload_excel_test", summary="Загрузить Excel файл с точками маршрута")
async def upload_excel(
    route_date: datetime = Form(...), 
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_session),
    idUser: UUID = Form(...)
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

        driver_id = idUser
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

