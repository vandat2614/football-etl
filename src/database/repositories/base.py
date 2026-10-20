"""
Base Repository class.
Provides common database operations using SQLAlchemy Session.
"""

from typing import Any, Generic, List, Optional, Type, TypeVar
from sqlalchemy import select
from sqlalchemy.orm import Session

T = TypeVar("T")


class BaseRepository(Generic[T]):
    """Generic repository providing standardized CRUD operations."""

    def __init__(self, session: Session, model_class: Type[T]):
        self.session = session
        self.model_class = model_class

    def get_by_id(self, entity_id: Any) -> Optional[T]:
        """Fetch a single record by its primary key."""
        return self.session.get(self.model_class, entity_id)

    def find_all(self) -> List[T]:
        """Retrieve all records for this entity."""
        stmt = select(self.model_class)
        return list(self.session.scalars(stmt).all())

    def upsert(self, entity: T) -> T:
        """Insert or update a record using session.merge()."""
        merged = self.session.merge(entity)
        return merged

    def upsert_many(self, entities: List[T]) -> List[T]:
        """Batch upsert multiple records."""
        results = [self.session.merge(e) for e in entities]
        return results
