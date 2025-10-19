from datetime import datetime
from fastapi import FastAPI, HTTPException, Query
import httpx
from pydantic import BaseModel
from database.database_app import create_db_if_not_exists, create_tables
from migration import run_auto_migrations
from fastapi.middleware.cors import CORSMiddleware
from routers import addresses, deliveryTypes, legalEntities, loading_places, loadings, stats, tariffs, transportCompanies, users, vehicles, logs, auth, trail, stores
from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete, or_, select
from database.database_app import get_session
from models import Address, DeliveryType, LegalEntityType, Loading, LoadingPlace, LoadingStatusLog, RoutePointStatusEnum, RouteStatusEnum, StatusEnum, Store, Tariff, TransportCompany, User, Vehicle, LogEntry, RoutePlan, RoutePoint, RoutePointStatusLog


create_db_if_not_exists()
create_tables()

# выполняем autogenerate+upgrade
# run_auto_migrations()

app = FastAPI(debug=True)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],  
    allow_headers=["*"],  
)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(vehicles.router)
app.include_router(logs.router)
app.include_router(trail.router)
app.include_router(stats.router)
app.include_router(addresses.router)
app.include_router(stores.router)
app.include_router(legalEntities.router)
app.include_router(deliveryTypes.router)
app.include_router(transportCompanies.router)
app.include_router(tariffs.router)
app.include_router(loading_places.router)
app.include_router(loadings.router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],  
    allow_headers=["*"],  
)


# Определение модели для ответа
class GeocodeResponse(BaseModel):
    lat: float
    lng: float

@app.get("/geocode")
async def geocode(address: str):
    url = f"https://nominatim.openstreetmap.org/search?format=json&q={address}"

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers={"User-Agent": "YourAppName (contact@yourapp.com)"})
            response.raise_for_status()  
            data = response.json()
            
            if not data:
                raise HTTPException(status_code=404, detail="Address not found")
            
            return GeocodeResponse(lat=float(data[0]["lat"]), lng=float(data[0]["lon"]))
        
        except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=e.response.status_code, detail=f"HTTP error occurred: {e}")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse
import httpx
import pandas as pd
from io import BytesIO

@app.post("/apply-migrations", summary="Автоматическое применение миграций")
async def apply_migrations():
    try:
        run_auto_migrations()
        return {"message": "Миграции успешно применены"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@app.post("/geocode_excel")
async def geocode_excel(file: UploadFile = File(...)):
    # Проверка формата файла
    if not file.filename.endswith((".xls", ".xlsx")):
        raise HTTPException(status_code=400, detail="Файл должен быть в формате Excel (.xls или .xlsx)")

    # Чтение Excel-файла
    try:
        contents = await file.read()
        df = pd.read_excel(BytesIO(contents))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Ошибка чтения Excel: {str(e)}")

    # Проверка, что есть хотя бы один столбец
    if df.shape[1] < 1:
        raise HTTPException(status_code=400, detail="Файл должен содержать хотя бы один столбец с адресами")

    # Берём первый столбец как адреса
    address_col = df.columns[0]
    addresses = df[address_col].astype(str).tolist()

    results = []
    async with httpx.AsyncClient() as client:
        for address in addresses:
            try:
                url = "https://nominatim.openstreetmap.org/search"
                params = {"format": "json", "q": address}
                headers = {"User-Agent": "YourAppName (contact@yourapp.com)"}

                resp = await client.get(url, params=params, headers=headers)
                resp.raise_for_status()
                data = resp.json()

                if data:
                    lat = float(data[0]["lat"])
                    lon = float(data[0]["lon"])
                else:
                    lat, lon = None, None

                results.append({"address": address, "lat": lat, "lon": lon})
            except Exception:
                results.append({"address": address, "lat": None, "lon": None})

    # Создаём новый Excel с координатами
    result_df = pd.DataFrame(results)
    output = BytesIO()
    result_df.to_excel(output, index=False)
    output.seek(0)

    # Возвращаем Excel как файл
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": 'attachment; filename="geocoded_addresses.xlsx"'
        },
    )

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
@app.post("/filter_addresses")
async def filter_addresses(
    file: UploadFile = File(...),
    keyword: str = Form(...)
):
    # Проверка формата файла
    if not file.filename.endswith((".xls", ".xlsx")):
        raise HTTPException(status_code=400, detail="Файл должен быть в формате Excel (.xls или .xlsx)")

    # Чтение Excel-файла
    try:
        contents = await file.read()
        df = pd.read_excel(BytesIO(contents))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Ошибка чтения Excel: {str(e)}")

    # Проверяем, что есть хотя бы один столбец
    if df.shape[1] < 1:
        raise HTTPException(status_code=400, detail="Файл должен содержать хотя бы один столбец с адресами")

    # Берём первый столбец как адреса
    address_col = df.columns[0]

    # Фильтрация: удаляем строки, где встречается ключевое слово (нечувствительно к регистру)
    df_filtered = df[~df[address_col].astype(str).str.contains(keyword, case=False, na=False)]

    # Сохраняем результат в Excel
    output = BytesIO()
    df_filtered.to_excel(output, index=False)
    output.seek(0)

    # Возвращаем файл пользователю
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": 'attachment; filename="filtered_addresses.xlsx"'
        },
    )

@app.post("/clear_database", summary="Очистить все таблицы базы данных")
async def clear_database(db: AsyncSession = Depends(get_session)):
    try:
        await db.execute(delete(RoutePointStatusLog))
        await db.execute(delete(RoutePoint))
        await db.execute(delete(RoutePlan))
        await db.execute(delete(LogEntry))
        await db.execute(delete(Vehicle))
        await db.execute(delete(User))

        await db.commit()
        return {"detail": "База данных успешно очищена"}
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Ошибка при очистке базы: {e}")





@app.get("/get_changes", summary="Получить объекты, созданные или изменённые после даты")
async def get_changes(
    since: datetime = Query(..., description="Дата и время для фильтрации в формате 2025-10-19T10:00:00"),
    db: AsyncSession = Depends(get_session)
):
    results = {}

    models_to_check = {
        "directories": { 
            "users": User,
            "vehicles": Vehicle,
            "transport_companies": TransportCompany,
            "addresses": Address,
            "stores": Store,
            "tariffs": Tariff,
            "loading_places": LoadingPlace,
        },
        "static_directories": {  
            "legal_entity_types": LegalEntityType,
            "delivery_types": DeliveryType,
            "status_enums": StatusEnum,
            "route_status_enums": RouteStatusEnum,
            "route_point_status_enums": RoutePointStatusEnum,
        },
        "documents": { 
            "route_plans": RoutePlan,
            "route_points": RoutePoint,
            "loadings": Loading,
            "log_entries": LogEntry,
            "route_point_status_logs": RoutePointStatusLog,
            "loading_status_logs": LoadingStatusLog,
        }
    }


    for key, model in models_to_check.items():
        query = await db.execute(
            select(model).filter(
                or_(
                    model.createDateTime > since,
                    model.changeDateTime > since
                )
            )
        )
        results[key] = [obj.__dict__ for obj in query.scalars().all()]

        for obj in results[key]:
            obj.pop("_sa_instance_state", None)

    return results