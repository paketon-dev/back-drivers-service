from typing import List
from fastapi import FastAPI, HTTPException
import httpx
from pydantic import BaseModel
from database.database_app import create_db_if_not_exists, create_tables
from migration import run_auto_migrations
from fastapi.middleware.cors import CORSMiddleware
from routers import stats, users, vehicles, logs, auth, trail

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
    # Формируем запрос к OpenStreetMap Nominatim API
    url = f"https://nominatim.openstreetmap.org/search?format=json&q={address}"

    # Инициализируем httpx клиент для асинхронных запросов
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers={"User-Agent": "YourAppName (contact@yourapp.com)"})
            response.raise_for_status()  # Проверяем на ошибки
            data = response.json()
            
            if not data:
                raise HTTPException(status_code=404, detail="Address not found")
            
            # Возвращаем первый результат с координатами
            return GeocodeResponse(lat=float(data[0]["lat"]), lng=float(data[0]["lon"]))
        
        except httpx.HTTPStatusError as e:
            # Ошибка HTTP статуса
            raise HTTPException(status_code=e.response.status_code, detail=f"HTTP error occurred: {e}")
        except Exception as e:
            # Другие ошибки
            raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")


from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete
from database.database_app import get_session  # ваш Dependency для сессии
from models import User, Vehicle, LogEntry, RoutePlan, RoutePoint, RoutePointStatusLog



@app.post("/clear_database", summary="Очистить все таблицы базы данных")
async def clear_database(db: AsyncSession = Depends(get_session)):
    try:
        # Важно соблюдать порядок удаления из-за ForeignKey
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
