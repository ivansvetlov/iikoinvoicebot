"""Модели базы данных."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, func
from sqlalchemy.orm import declarative_base


Base = declarative_base()


class TaskRecord(Base):
    """Запись о задаче обработки накладной."""

    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    request_id = Column(String(64), unique=True, index=True, nullable=False)
    status = Column(String(32), nullable=False, default="queued")

    user_id = Column(String(64), nullable=True)
    chat_id = Column(String(64), nullable=True)
    filename = Column(String(256), nullable=True)
    batch = Column(Boolean, nullable=False, default=False)
    push_to_iiko = Column(Boolean, nullable=False, default=True)
    pdf_mode = Column(String(32), nullable=True)

    iiko_uploaded = Column(Boolean, nullable=True)
    iiko_error = Column(Text, nullable=True)
    message = Column(Text, nullable=True)
    result_json = Column(Text, nullable=True)

    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())

    finished_at = Column(DateTime, nullable=True)
    error = Column(Text, nullable=True)
