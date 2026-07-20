"""Cross-dialect column types.

Production runs on PostgreSQL (native UUID + JSONB). Tests run against SQLite for
speed/no-infra-required CI, so these TypeDecorators fall back to portable
representations (CHAR(36) / JSON text) there while using the native, more efficient
types on PostgreSQL.
"""
from __future__ import annotations

import uuid

from sqlalchemy import CHAR, JSON, TypeDecorator
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID


class GUID(TypeDecorator):
    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PGUUID(as_uuid=True))
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        if dialect.name == "postgresql":
            return str(value)
        if not isinstance(value, uuid.UUID):
            return str(uuid.UUID(value))
        return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        if isinstance(value, uuid.UUID):
            return value
        return uuid.UUID(value)


class PortableJSON(TypeDecorator):
    """JSONB on Postgres, JSON everywhere else."""

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB())
        return dialect.type_descriptor(JSON())
