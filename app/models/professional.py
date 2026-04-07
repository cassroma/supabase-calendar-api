from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Professional(Base):
    __tablename__ = "professionals"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    display_name: Mapped[str] = mapped_column(String(120), index=True)
    timezone: Mapped[str] = mapped_column(String(80), default="America/Sao_Paulo")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="professionals")
    services = relationship("Service", back_populates="professional")
    weekly_availabilities = relationship("WeeklyAvailability", back_populates="professional")
    appointments = relationship("Appointment", back_populates="professional")
