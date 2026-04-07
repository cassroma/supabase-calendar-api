from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Service(Base):
    __tablename__ = "services"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    professional_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("professionals.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(120), index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_minutes: Mapped[int] = mapped_column(Integer)
    price: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    professional = relationship("Professional", back_populates="services")
    appointments = relationship("Appointment", back_populates="service")
