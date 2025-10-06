from fastapi import FastAPI, HTTPException
import httpx
from pydantic import BaseModel
from database.database_app import create_db_if_not_exists, create_tables
from migration import run_auto_migrations
from fastapi.middleware.cors import CORSMiddleware
from routers import addresses, deliveryTypes, legalEntities, stats, tariffs, transportCompanies, users, vehicles, logs, auth, trail, stores
from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete
from database.database_app import get_session
from models import User, Vehicle, LogEntry, RoutePlan, RoutePoint, RoutePointStatusLog


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
