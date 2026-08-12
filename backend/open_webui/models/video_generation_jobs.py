from __future__ import annotations

import time
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import BigInteger, Column, ForeignKey, Integer, String, Text

from open_webui.internal.db import Base, get_db


VIDEO_JOB_STATUSES = {
    "submitting",
    "pending",
    "downloading",
    "completed",
    "failed",
    "timed_out",
}
VIDEO_JOB_ACTIVE_STATUSES = {"submitting", "pending", "downloading"}


class VideoGenerationJob(Base):
    __tablename__ = "video_generation_job"

    id = Column(String, primary_key=True)
    user_id = Column(String, nullable=False, index=True)
    model_selection_id = Column(Text, nullable=False)
    model_id = Column(Text, nullable=False)
    provider = Column(String, nullable=False, default="openai")
    source = Column(String, nullable=False, default="personal")
    connection_id = Column(String, nullable=True)
    connection_index = Column(String, nullable=True)
    credential_entry_id = Column(String, nullable=True)
    upstream_request_id = Column(String, nullable=True, index=True)
    prompt = Column(Text, nullable=True)
    duration = Column(Integer, nullable=False)
    aspect_ratio = Column(String, nullable=False)
    resolution = Column(String, nullable=False)
    reference_file_id = Column(
        String,
        ForeignKey("file.id", ondelete="SET NULL"),
        nullable=True,
    )
    status = Column(String, nullable=False, index=True)
    progress = Column(Integer, nullable=True)
    error_code = Column(String, nullable=True)
    error_message = Column(Text, nullable=True)
    result_file_id = Column(
        String,
        ForeignKey("file.id", ondelete="SET NULL"),
        nullable=True,
    )
    submitted_at = Column(BigInteger, nullable=True)
    next_poll_at = Column(BigInteger, nullable=True, index=True)
    last_polled_at = Column(BigInteger, nullable=True)
    attempt_count = Column(Integer, nullable=False, default=0)
    created_at = Column(BigInteger, nullable=False)
    updated_at = Column(BigInteger, nullable=False)
    completed_at = Column(BigInteger, nullable=True)


class VideoGenerationJobForm(BaseModel):
    model_selection_id: str
    model_id: str
    provider: str = "openai"
    source: str = "personal"
    connection_id: Optional[str] = None
    connection_index: Optional[str] = None
    credential_entry_id: Optional[str] = None
    upstream_request_id: Optional[str] = None
    prompt: Optional[str] = None
    duration: int = Field(ge=1, le=15)
    aspect_ratio: str
    resolution: str
    reference_file_id: Optional[str] = None
    status: str = "submitting"
    progress: Optional[int] = 0
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    result_file_id: Optional[str] = None
    submitted_at: Optional[int] = None
    next_poll_at: Optional[int] = None
    last_polled_at: Optional[int] = None
    attempt_count: int = 0
    model_config = ConfigDict(extra="forbid")


class VideoGenerationJobModel(BaseModel):
    id: str
    user_id: str
    model_selection_id: str
    model_id: str
    provider: str
    source: str
    connection_id: Optional[str] = None
    connection_index: Optional[str] = None
    credential_entry_id: Optional[str] = None
    upstream_request_id: Optional[str] = None
    prompt: Optional[str] = None
    duration: int
    aspect_ratio: str
    resolution: str
    reference_file_id: Optional[str] = None
    status: str
    progress: Optional[int] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    result_file_id: Optional[str] = None
    submitted_at: Optional[int] = None
    next_poll_at: Optional[int] = None
    last_polled_at: Optional[int] = None
    attempt_count: int = 0
    created_at: int
    updated_at: int
    completed_at: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class VideoGenerationJobsTable:
    @staticmethod
    def _validate_status(status: str) -> str:
        normalized = str(status or "").strip().lower()
        if normalized not in VIDEO_JOB_STATUSES:
            raise ValueError(f"Unsupported video generation job status: {status}")
        return normalized

    def insert_new_job(
        self, user_id: str, form_data: VideoGenerationJobForm
    ) -> Optional[VideoGenerationJobModel]:
        now = int(time.time())
        payload = form_data.model_dump()
        payload["status"] = self._validate_status(payload.get("status", "submitting"))
        payload.setdefault("submitted_at", now)
        payload.update({"id": payload.get("id") or None, "created_at": now, "updated_at": now})
        payload.pop("id", None)

        # The API assigns IDs before calling this method so the upstream request and
        # the durable job can be correlated without storing any provider payload.
        job_id = str(payload.pop("job_id", "") or "")
        if not job_id:
            import uuid

            job_id = str(uuid.uuid4())

        try:
            with get_db() as db:
                result = VideoGenerationJob(
                    id=job_id,
                    user_id=user_id,
                    **payload,
                )
                db.add(result)
                db.commit()
                db.refresh(result)
                return VideoGenerationJobModel.model_validate(result)
        except Exception:
            return None

    def get_job_by_id(self, job_id: str) -> Optional[VideoGenerationJobModel]:
        with get_db() as db:
            result = db.get(VideoGenerationJob, job_id)
            return VideoGenerationJobModel.model_validate(result) if result else None

    def get_job_by_id_and_user_id(
        self, job_id: str, user_id: str
    ) -> Optional[VideoGenerationJobModel]:
        with get_db() as db:
            result = (
                db.query(VideoGenerationJob)
                .filter(
                    VideoGenerationJob.id == job_id,
                    VideoGenerationJob.user_id == user_id,
                )
                .first()
            )
            return VideoGenerationJobModel.model_validate(result) if result else None

    def get_jobs_by_user_id(
        self, user_id: str, *, skip: int = 0, limit: int = 50
    ) -> list[VideoGenerationJobModel]:
        with get_db() as db:
            results = (
                db.query(VideoGenerationJob)
                .filter(VideoGenerationJob.user_id == user_id)
                .order_by(VideoGenerationJob.created_at.desc())
                .offset(skip)
                .limit(limit)
                .all()
            )
            return [VideoGenerationJobModel.model_validate(row) for row in results]

    def get_due_jobs(self, *, now: Optional[int] = None, limit: int = 20) -> list[VideoGenerationJobModel]:
        due_at = int(time.time() if now is None else now)
        with get_db() as db:
            results = (
                db.query(VideoGenerationJob)
                .filter(
                    VideoGenerationJob.status.in_(VIDEO_JOB_ACTIVE_STATUSES),
                    (VideoGenerationJob.next_poll_at.is_(None))
                    | (VideoGenerationJob.next_poll_at <= due_at),
                )
                .order_by(VideoGenerationJob.created_at.asc())
                .limit(limit)
                .all()
            )
            return [VideoGenerationJobModel.model_validate(row) for row in results]

    def update_job_by_id(self, job_id: str, **updates: Any) -> Optional[VideoGenerationJobModel]:
        if "status" in updates:
            updates["status"] = self._validate_status(updates["status"])
        updates["updated_at"] = int(time.time())
        with get_db() as db:
            result = (
                db.query(VideoGenerationJob)
                .filter(VideoGenerationJob.id == job_id)
                .update(updates, synchronize_session=False)
            )
            if not result:
                return None
            db.commit()
            row = db.get(VideoGenerationJob, job_id)
            return VideoGenerationJobModel.model_validate(row) if row else None

    def claim_job(
        self,
        job_id: str,
        expected_status: str,
        *,
        lease_seconds: int = 300,
    ) -> Optional[VideoGenerationJobModel]:
        """Atomically lease one due job so another worker cannot process it concurrently."""
        expected_status = self._validate_status(expected_status)
        now = int(time.time())
        with get_db() as db:
            updated = (
                db.query(VideoGenerationJob)
                .filter(
                    VideoGenerationJob.id == job_id,
                    VideoGenerationJob.status == expected_status,
                    (VideoGenerationJob.next_poll_at.is_(None))
                    | (VideoGenerationJob.next_poll_at <= now),
                )
                .update(
                    {
                        "next_poll_at": now + max(30, int(lease_seconds)),
                        "updated_at": now,
                    },
                    synchronize_session=False,
                )
            )
            if not updated:
                return None
            db.commit()
            row = db.get(VideoGenerationJob, job_id)
            return VideoGenerationJobModel.model_validate(row) if row else None

    def delete_job_by_id(self, job_id: str) -> bool:
        with get_db() as db:
            result = db.query(VideoGenerationJob).filter_by(id=job_id).delete()
            db.commit()
            return result > 0

    def delete_jobs_by_user_id(self, user_id: str) -> bool:
        with get_db() as db:
            db.query(VideoGenerationJob).filter_by(user_id=user_id).delete()
            db.commit()
            return True


VideoGenerationJobs = VideoGenerationJobsTable()


__all__ = [
    "VIDEO_JOB_ACTIVE_STATUSES",
    "VIDEO_JOB_STATUSES",
    "VideoGenerationJob",
    "VideoGenerationJobForm",
    "VideoGenerationJobModel",
    "VideoGenerationJobs",
]
