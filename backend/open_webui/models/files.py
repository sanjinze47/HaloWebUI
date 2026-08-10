import json
import logging
import time
from typing import Optional

from open_webui.internal.db import Base, JSONField, get_db
from open_webui.env import SRC_LOG_LEVELS
from pydantic import BaseModel, ConfigDict
from sqlalchemy import BigInteger, Column, String, Text, JSON

log = logging.getLogger(__name__)
log.setLevel(SRC_LOG_LEVELS["MODELS"])

####################
# Files DB Schema
####################


class File(Base):
    __tablename__ = "file"
    id = Column(String, primary_key=True)
    user_id = Column(String)
    hash = Column(Text, nullable=True)

    filename = Column(Text)
    path = Column(Text, nullable=True)

    data = Column(JSON, nullable=True)
    meta = Column(JSON, nullable=True)

    access_control = Column(JSON, nullable=True)

    created_at = Column(BigInteger)
    updated_at = Column(BigInteger)


class FileModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    hash: Optional[str] = None

    filename: str
    path: Optional[str] = None

    data: Optional[dict] = None
    meta: Optional[dict] = None

    access_control: Optional[dict] = None

    created_at: Optional[int]  # timestamp in epoch
    updated_at: Optional[int]  # timestamp in epoch


####################
# Forms
####################


class FileMeta(BaseModel):
    name: Optional[str] = None
    content_type: Optional[str] = None
    size: Optional[int] = None

    model_config = ConfigDict(extra="allow")


class FileDiagnostic(BaseModel):
    code: str
    title: str
    message: str
    hint: str
    blocking: bool = True


class FileModelResponse(BaseModel):
    id: str
    user_id: str
    hash: Optional[str] = None

    filename: str
    data: Optional[dict] = None
    meta: FileMeta

    created_at: int  # timestamp in epoch
    updated_at: int  # timestamp in epoch
    error: Optional[str] = None
    diagnostic: Optional[FileDiagnostic] = None

    model_config = ConfigDict(extra="allow")


class FileMetadataResponse(BaseModel):
    id: str
    meta: dict
    created_at: int  # timestamp in epoch
    updated_at: int  # timestamp in epoch


class FileForm(BaseModel):
    id: str
    hash: Optional[str] = None
    filename: str
    path: str
    data: dict = {}
    meta: dict = {}
    access_control: Optional[dict] = None


class FilesTable:
    @staticmethod
    def _is_pending_deletion(file) -> bool:
        return bool((file.meta or {}).get("deletion_pending"))

    def insert_new_file(self, user_id: str, form_data: FileForm) -> Optional[FileModel]:
        with get_db() as db:
            file = FileModel(
                **{
                    **form_data.model_dump(),
                    "user_id": user_id,
                    "created_at": int(time.time()),
                    "updated_at": int(time.time()),
                }
            )

            try:
                result = File(**file.model_dump())
                db.add(result)
                db.commit()
                db.refresh(result)
                if result:
                    return FileModel.model_validate(result)
                else:
                    return None
            except Exception as e:
                log.exception(f"Error inserting a new file: {e}")
                return None

    def get_file_by_id(
        self, id: str, *, include_pending: bool = False
    ) -> Optional[FileModel]:
        with get_db() as db:
            try:
                file = db.get(File, id)
                if not file or (
                    not include_pending and self._is_pending_deletion(file)
                ):
                    return None
                return FileModel.model_validate(file)
            except Exception:
                return None

    def get_file_metadata_by_id(
        self, id: str, *, include_pending: bool = False
    ) -> Optional[FileMetadataResponse]:
        with get_db() as db:
            try:
                file = db.get(File, id)
                if not file or (
                    not include_pending and self._is_pending_deletion(file)
                ):
                    return None
                return FileMetadataResponse(
                    id=file.id,
                    meta=file.meta,
                    created_at=file.created_at,
                    updated_at=file.updated_at,
                )
            except Exception:
                return None

    def get_files(self, *, include_pending: bool = False) -> list[FileModel]:
        with get_db() as db:
            return [
                FileModel.model_validate(file)
                for file in db.query(File).all()
                if include_pending or not self._is_pending_deletion(file)
            ]

    def get_files_by_ids(self, ids: list[str]) -> list[FileModel]:
        with get_db() as db:
            return [
                FileModel.model_validate(file)
                for file in db.query(File)
                .filter(File.id.in_(ids))
                .order_by(File.updated_at.desc())
                .all()
                if not self._is_pending_deletion(file)
            ]

    def get_file_metadatas_by_ids(self, ids: list[str]) -> list[FileMetadataResponse]:
        with get_db() as db:
            return [
                FileMetadataResponse(
                    id=file.id,
                    meta=file.meta,
                    created_at=file.created_at,
                    updated_at=file.updated_at,
                )
                for file in db.query(File)
                .filter(File.id.in_(ids))
                .order_by(File.updated_at.desc())
                .all()
                if not self._is_pending_deletion(file)
            ]

    def get_files_by_user_id(
        self, user_id: str, *, include_pending: bool = False
    ) -> list[FileModel]:
        with get_db() as db:
            return [
                FileModel.model_validate(file)
                for file in db.query(File)
                .filter_by(user_id=user_id)
                .order_by(File.created_at.desc(), File.id.desc())
                .all()
                if include_pending or not self._is_pending_deletion(file)
            ]

    def get_file_by_hash_and_user_id(
        self, user_id: str, hash: str
    ) -> Optional[FileModel]:
        with get_db() as db:
            try:
                file = db.query(File).filter_by(user_id=user_id, hash=hash).first()
                if file and self._is_pending_deletion(file):
                    return None
                return FileModel.model_validate(file) if file else None
            except Exception:
                return None

    def update_file_hash_by_id(self, id: str, hash: str) -> Optional[FileModel]:
        with get_db() as db:
            try:
                file = db.query(File).filter_by(id=id).first()
                file.hash = hash
                db.commit()

                return FileModel.model_validate(file)
            except Exception:
                return None

    def update_file_data_by_id(self, id: str, data: dict) -> Optional[FileModel]:
        with get_db() as db:
            try:
                file = db.query(File).filter_by(id=id).first()
                file.data = {**(file.data if file.data else {}), **data}
                db.commit()
                return FileModel.model_validate(file)
            except Exception as e:

                return None

    def update_file_metadata_by_id(self, id: str, meta: dict) -> Optional[FileModel]:
        with get_db() as db:
            try:
                file = db.query(File).filter_by(id=id).first()
                merged = {**(file.meta if file.meta else {}), **meta}
                # Sanitize: roundtrip through JSON to catch non-serializable values
                file.meta = json.loads(json.dumps(merged, default=str))
                db.commit()
                return FileModel.model_validate(file)
            except Exception:
                return None

    def update_file_processing_by_id(
        self, id: str, *, data: dict, hash: str, meta: dict
    ) -> Optional[FileModel]:
        """Commit content, hash and processing metadata as one database state."""
        with get_db() as db:
            try:
                file = db.query(File).filter_by(id=id).first()
                if not file:
                    return None
                file.data = {**(file.data or {}), **data}
                file.hash = hash
                file.meta = json.loads(
                    json.dumps({**(file.meta or {}), **meta}, default=str)
                )
                file.updated_at = int(time.time())
                db.commit()
                db.refresh(file)
                return FileModel.model_validate(file)
            except Exception:
                db.rollback()
                return None

    def update_file_access_control_by_id(
        self, id: str, access_control: Optional[dict]
    ) -> Optional[FileModel]:
        with get_db() as db:
            try:
                file = db.query(File).filter_by(id=id).first()
                file.access_control = (
                    json.loads(json.dumps(access_control, default=str))
                    if access_control is not None
                    else None
                )
                db.commit()
                return FileModel.model_validate(file)
            except Exception:
                return None

    def delete_file_by_id(self, id: str) -> bool:
        with get_db() as db:
            try:
                db.query(File).filter_by(id=id).delete()
                db.commit()

                return True
            except Exception:
                return False

    def delete_all_files(self) -> bool:
        with get_db() as db:
            try:
                db.query(File).delete()
                db.commit()

                return True
            except Exception:
                return False

    def delete_files_by_user_id(self, user_id: str) -> bool:
        with get_db() as db:
            try:
                db.query(File).filter_by(user_id=user_id).delete()
                db.commit()
                return True
            except Exception:
                return False


Files = FilesTable()
