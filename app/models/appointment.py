from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Appointment(Base):
    __tablename__ = "appointments"
    __table_args__ = (
        UniqueConstraint("professional_id", "starts_at", name="uq_appointment_professional_start"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    professional_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("professionals.id", ondelete="CASCADE"), index=True
    )
    service_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("services.id", ondelete="RESTRICT"), index=True
    )
    customer_name: Mapped[str] = mapped_column(String(120))
    customer_phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    customer_email: Mapped[str | None] = mapped_column(String(150), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="scheduled", index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    professional = relationship("Professional", back_populates="appointments")
    service = relationship("Service", back_populates="appointments")
