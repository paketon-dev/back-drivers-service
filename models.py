from datetime import datetime
from sqlalchemy import (
    Boolean, Column, Integer, String, ForeignKey, DateTime, Float, Enum
)
from sqlalchemy.orm import relationship, declarative_base
import enum

Base = declarative_base()


# ===================== Пользователь =====================
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, nullable=False)
    hashed_password = Column(String, nullable=False)
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    middle_name = Column(String, nullable=True)
    rate = Column(Float, nullable=True)
    is_active = Column(Boolean, default=True)

    vehicles = relationship("Vehicle", back_populates="owner")
    tariffs = relationship("Tariff", back_populates="user")
    transport_company = relationship("TransportCompany", back_populates="user", uselist=False)


# ===================== Тип юридического лица =====================
class LegalEntityType(Base):
    __tablename__ = "legal_entity_types"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)

    companies = relationship("TransportCompany", back_populates="legal_entity_type")


# ===================== Транспортная компания =====================
class TransportCompany(Base):
    __tablename__ = "transport_companies"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    inn = Column(String, nullable=False)
    kpp = Column(String, nullable=True)
    contacts = Column(String, nullable=True)

    legal_entity_type_id = Column(Integer, ForeignKey("legal_entity_types.id"))
    user_id = Column(Integer, ForeignKey("users.id"))

    legal_entity_type = relationship("LegalEntityType", back_populates="companies")
    user = relationship("User", back_populates="transport_company")


# ===================== Транспортное средство =====================
class Vehicle(Base):
    __tablename__ = "vehicles"

    id = Column(Integer, primary_key=True, index=True)
    plate_number = Column(String, unique=True, index=True)
    model = Column(String)

    owner_id = Column(Integer, ForeignKey("users.id"))
    owner = relationship("User", back_populates="vehicles")

    logs = relationship("LogEntry", back_populates="vehicle")
    route_plans = relationship("RoutePlan", back_populates="vehicle")


# ===================== Статусы ТС =====================
class StatusEnum(str, enum.Enum):
    idle = "idle"
    loading = "loading"
    in_transit = "in_transit"
    delivered = "delivered"
    work_start = "work_start"
    work_end = "work_end"


# ===================== Логи транспортных средств =====================
class LogEntry(Base):
    __tablename__ = "logs"

    id = Column(Integer, primary_key=True, index=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"))
    status = Column(Enum(StatusEnum), default=StatusEnum.idle)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    timestamp = Column(DateTime(timezone=True), default=datetime.utcnow)

    vehicle = relationship("Vehicle", back_populates="logs")


# ===================== Тип доставки =====================
class DeliveryType(Base):
    __tablename__ = "delivery_types"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)

    routes = relationship("RoutePlan", back_populates="delivery_type")


# ===================== Статусы маршрута =====================
class RouteStatusEnum(str, enum.Enum):
    planned = "planned"
    in_progress = "in_progress"
    completed = "completed"


# ===================== План маршрута =====================
class RoutePlan(Base):
    __tablename__ = "route_plans"

    id = Column(Integer, primary_key=True, index=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"))
    date = Column(DateTime(timezone=True), default=datetime.utcnow)
    status = Column(Enum(RouteStatusEnum), default=RouteStatusEnum.planned)
    notes = Column(String, nullable=True)

    delivery_type_id = Column(Integer, ForeignKey("delivery_types.id"), nullable=True)

    vehicle = relationship("Vehicle", back_populates="route_plans")
    delivery_type = relationship("DeliveryType", back_populates="routes")
    points = relationship("RoutePoint", back_populates="route_plan", cascade="all, delete-orphan")


# ===================== Статусы точки маршрута =====================
class RoutePointStatusEnum(str, enum.Enum):
    planned = "planned"
    en_route = "en_route"
    arrived = "arrived"
    completed = "completed"
    skipped = "skipped"


# ===================== Адрес =====================
class Address(Base):
    __tablename__ = "addresses"

    id = Column(Integer, primary_key=True, index=True)
    address_1c = Column(String, nullable=False)
    country = Column(String, nullable=True)
    region = Column(String, nullable=True)
    area = Column(String, nullable=True)
    city = Column(String, nullable=True)
    street = Column(String, nullable=True)
    house = Column(String, nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)

    stores = relationship("Store", back_populates="address")
    route_points = relationship("RoutePoint", back_populates="address")


# ===================== Магазин =====================
class Store(Base):
    __tablename__ = "stores"

    id = Column(Integer, primary_key=True, index=True)
    uuid_1c = Column(String, nullable=False, unique=True)
    name_1c = Column(String, nullable=False)
    address_id = Column(Integer, ForeignKey("addresses.id"))

    address = relationship("Address", back_populates="stores")
    route_points = relationship("RoutePoint", back_populates="store")


# ===================== Точка маршрута =====================
class RoutePoint(Base):
    __tablename__ = "route_points"

    id = Column(Integer, primary_key=True, index=True)
    route_plan_id = Column(Integer, ForeignKey("route_plans.id"))
    order = Column(Integer, nullable=False)
    doc = Column(String, nullable=True)
    payment = Column(Float, nullable=True)
    counterparty = Column(String, nullable=True)
    arrival_time = Column(DateTime(timezone=True), nullable=True)
    departure_time = Column(DateTime(timezone=True), nullable=True)
    duration_minutes = Column(Integer, nullable=True)
    note = Column(String, nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    status = Column(Enum(RoutePointStatusEnum), default=RoutePointStatusEnum.planned)

    address_id = Column(Integer, ForeignKey("addresses.id"), nullable=True)
    store_id = Column(Integer, ForeignKey("stores.id"), nullable=True)

    route_plan = relationship("RoutePlan", back_populates="points")
    address = relationship("Address", back_populates="route_points")
    store = relationship("Store", back_populates="route_points")

    status_logs = relationship(
        "RoutePointStatusLog",
        back_populates="point",
        cascade="all, delete-orphan",
        order_by="RoutePointStatusLog.timestamp"
    )


# ===================== Лог статусов точки маршрута =====================
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


# ===================== Тарифы =====================
class Tariff(Base):
    __tablename__ = "tariffs"

    id = Column(Integer, primary_key=True, index=True)
    vehicle_type = Column(String, nullable=False)
    city = Column(String, nullable=True)
    unit = Column(String, nullable=True)
    min_payment = Column(Float, nullable=True)
    min_volume = Column(Float, nullable=True)
    max_volume = Column(Float, nullable=True)
    body_type = Column(String, nullable=True)
    description = Column(String, nullable=True)

    user_id = Column(Integer, ForeignKey("users.id"))
    user = relationship("User", back_populates="tariffs")
