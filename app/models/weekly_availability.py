from __future__ import annotations

import uuid
from datetime import datetime, time

from sqlalchemy import DateTime, ForeignKey, Integer, Time, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class WeeklyAvailability(Base):
    __tablename__ = "weekly_availabilities"
    __table_args__ = (
        UniqueConstraint(
            "professional_id",
            "weekday",
            "start_time",
            "end_time",
            name="uq_weekly_availability_slot",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    professional_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("professionals.id", ondelete="CASCADE"), index=True
    )
    weekday: Mapped[int] = mapped_column(Integer, index=True)  # 0=segunda, 6=domingo
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    professional = relationship("Professional", back_populates="weekly_availabilities")
