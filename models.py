from datetime import datetime
from sqlalchemy import Boolean, Column, Integer, String, ForeignKey, DateTime, Float, Enum, func
from sqlalchemy.orm import relationship, declarative_base
import enum

Base = declarative_base() 

# Пользователь
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, nullable=False)
    hashed_password = Column(String, nullable=False)
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    middle_name = Column(String, nullable=True)
    rate = Column(Float, nullable=True)  # тариф
    is_active = Column(Boolean, default=True)
    
    vehicles = relationship("Vehicle", back_populates="owner")


# Транспортное средство
class Vehicle(Base):
    __tablename__ = "vehicles"  

    id = Column(Integer, primary_key=True, index=True)  # Уникальный идентификатор транспортного средства
    plate_number = Column(String, unique=True, index=True)  # Уникальный номерной знак
    model = Column(String)  # Модель транспортного средства

    owner_id = Column(Integer, ForeignKey("users.id"))  # Внешний ключ для связи с пользователем
    # Связь с пользователем - транспортное средство принадлежит пользователю
    owner = relationship("User", back_populates="vehicles")

    # Связь с таблицей "logs" - каждое транспортное средство может иметь несколько записей в логе
    logs = relationship("LogEntry", back_populates="vehicle")
    route_plans = relationship("RoutePlan", back_populates="vehicle")

# Перечисление статусов транспортного средства
class StatusEnum(str, enum.Enum):
    idle = "idle"  # Ожидание
    loading = "loading"  # Загрузка
    in_transit = "in_transit"  # В пути
    delivered = "delivered"  # Доставлено
    work_start = "work_start"  # Начало смены
    work_end = "work_end"      # Конец смены

# Модель записи в логе
class LogEntry(Base):
    __tablename__ = "logs"  # Название таблицы в базе данных

    id = Column(Integer, primary_key=True, index=True)  # Уникальный идентификатор записи
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"))  # Внешний ключ для связи с транспортным средством
    status = Column(Enum(StatusEnum), default=StatusEnum.idle)  # Статус транспортного средства (по умолчанию "idle")
    latitude = Column(Float, nullable=True)  # Широта местоположения
    longitude = Column(Float, nullable=True)  # Долгота местоположения
    timestamp = Column(DateTime(timezone=True))  # Время записи (по умолчанию текущее время)

    # Связь с транспортным средством - каждая запись в логе принадлежит определённому транспортному средству
    vehicle = relationship("Vehicle", back_populates="logs")

# Статусы маршрута
class RouteStatusEnum(str, enum.Enum):
    planned = "planned"       # Планируется
    in_progress = "in_progress"  # В процессе
    completed = "completed"   # Завершен

# Модель плана маршрута на день
class RoutePlan(Base):
    __tablename__ = "route_plans"

    id = Column(Integer, primary_key=True, index=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"))
    date = Column(DateTime(timezone=True), default=datetime.utcnow)  # дата маршрута
    status = Column(Enum(RouteStatusEnum), default=RouteStatusEnum.planned)
    notes = Column(String, nullable=True)  # Доп. заметки

    vehicle = relationship("Vehicle", back_populates="route_plans")
    points = relationship("RoutePoint", back_populates="route_plan", cascade="all, delete-orphan")


# Статусы точки маршрута
class RoutePointStatusEnum(str, enum.Enum):
    planned = "planned"          # точка запланирована, еще не начата
    en_route = "en_route"        # транспорт в пути к точке
    arrived = "arrived"          # транспорт прибыл, но работа еще не завершена
    completed = "completed"      # работа на точке завершена
    skipped = "skipped"          # точка пропущена

# Модель точки маршрута
class RoutePoint(Base):
    __tablename__ = "route_points"

    id = Column(Integer, primary_key=True, index=True)
    route_plan_id = Column(Integer, ForeignKey("route_plans.id"))
    order = Column(Integer, nullable=False)            # Порядковый номер точки
    doc = Column(String, nullable=True)                # Документ
    payment = Column(Float, nullable=True)            # Оплата
    counterparty = Column(String, nullable=True)      # Контрагент
    address = Column(String, nullable=False)          # Адрес или координаты
    arrival_time = Column(DateTime(timezone=True), nullable=True)      # Время прибытия
    departure_time = Column(DateTime(timezone=True), nullable=True)    # Время отъезда
    duration_minutes = Column(Integer, nullable=True)                  # Время на точку
    note = Column(String, nullable=True)
    latitude = Column(Float, nullable=True)  # Широта местоположения
    longitude = Column(Float, nullable=True)  # Долгота местоположения
    status = Column(Enum(RoutePointStatusEnum), default=RoutePointStatusEnum.planned)

    route_plan = relationship("RoutePlan", back_populates="points")
    status_logs = relationship(
    "RoutePointStatusLog",
    back_populates="point",
    cascade="all, delete-orphan",
    order_by="RoutePointStatusLog.timestamp"
)

class RoutePointStatusLog(Base):
    __tablename__ = "route_point_status_logs"

    id = Column(Integer, primary_key=True, index=True)
    point_id = Column(Integer, ForeignKey("route_points.id"), nullable=False)
    status = Column(Enum(RoutePointStatusEnum), nullable=False)
    timestamp = Column(DateTime(timezone=True), default=datetime.utcnow)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    note = Column(String, nullable=True)

    point = relationship("RoutePoint", back_populates="status_logs")
