"""Database metadata shared by the models and migrations."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """The base class of every database model."""
