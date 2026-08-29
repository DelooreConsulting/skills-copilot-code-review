"""
Announcement endpoints for the High School Management System API
"""

import uuid
from datetime import date
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..database import announcements_collection, teachers_collection

router = APIRouter(
    prefix="/announcements",
    tags=["announcements"]
)


class AnnouncementCreate(BaseModel):
    message: str = Field(..., min_length=1, max_length=500)
    start_date: Optional[str] = None
    expiration_date: str = Field(..., min_length=1)


class AnnouncementUpdate(BaseModel):
    message: Optional[str] = Field(default=None, min_length=1, max_length=500)
    start_date: Optional[str] = None
    expiration_date: Optional[str] = None


def _normalize_announcement(doc: Dict[str, Any]) -> Dict[str, Any]:
    announcement = dict(doc)
    announcement.pop("_id", None)
    announcement["id"] = str(doc.get("_id"))
    return announcement


def _validate_dates(start_date: Optional[str], expiration_date: Optional[str]) -> None:
    if not expiration_date:
        raise HTTPException(status_code=400, detail="Expiration date is required")

    try:
        expiration = date.fromisoformat(expiration_date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Expiration date must be in YYYY-MM-DD format") from exc

    if start_date:
        try:
            start = date.fromisoformat(start_date)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Start date must be in YYYY-MM-DD format") from exc

        if start > expiration:
            raise HTTPException(status_code=400, detail="Start date cannot be after the expiration date")

    if expiration < date.today():
        raise HTTPException(status_code=400, detail="Expiration date must be today or in the future")


@router.get("", response_model=List[Dict[str, Any]])
@router.get("/", response_model=List[Dict[str, Any]])
def get_announcements() -> List[Dict[str, Any]]:
    """Get all announcements, sorted by expiration date."""
    announcements = []
    for document in announcements_collection.find().sort("expiration_date", 1):
        announcement = _normalize_announcement(document)
        announcements.append(announcement)
    return announcements


@router.post("", response_model=Dict[str, Any])
def create_announcement(
    announcement: AnnouncementCreate,
    teacher_username: str = Query(...)
) -> Dict[str, Any]:
    """Create a new announcement. Requires signed-in teacher access."""
    teacher = teachers_collection.find_one({"_id": teacher_username})
    if not teacher:
        raise HTTPException(status_code=401, detail="Authentication required")

    _validate_dates(announcement.start_date, announcement.expiration_date)

    inserted = announcements_collection.insert_one({
        "_id": str(uuid.uuid4()),
        "message": announcement.message.strip(),
        "start_date": announcement.start_date,
        "expiration_date": announcement.expiration_date,
        "created_by": teacher_username,
    })

    created = announcements_collection.find_one({"_id": inserted.inserted_id})
    return _normalize_announcement(created)


@router.put("/{announcement_id}", response_model=Dict[str, Any])
def update_announcement(
    announcement_id: str,
    updates: AnnouncementUpdate,
    teacher_username: str = Query(...)
) -> Dict[str, Any]:
    """Update an announcement. Requires signed-in teacher access."""
    teacher = teachers_collection.find_one({"_id": teacher_username})
    if not teacher:
        raise HTTPException(status_code=401, detail="Authentication required")

    existing = announcements_collection.find_one({"_id": announcement_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Announcement not found")

    new_message = updates.message if updates.message is not None else existing.get("message")
    new_start_date = updates.start_date if updates.start_date is not None else existing.get("start_date")
    new_expiration_date = updates.expiration_date if updates.expiration_date is not None else existing.get("expiration_date")

    if not new_expiration_date:
        raise HTTPException(status_code=400, detail="Expiration date is required")

    _validate_dates(new_start_date, new_expiration_date)

    result = announcements_collection.update_one(
        {"_id": announcement_id},
        {"$set": {
            "message": new_message.strip(),
            "start_date": new_start_date,
            "expiration_date": new_expiration_date,
        }}
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Announcement not found")
    updated = announcements_collection.find_one({"_id": announcement_id})
    return _normalize_announcement(updated)


@router.delete("/{announcement_id}", response_model=Dict[str, Any])
def delete_announcement(
    announcement_id: str,
    teacher_username: str = Query(...)
) -> Dict[str, Any]:
    """Delete an announcement. Requires signed-in teacher access."""
    teacher = teachers_collection.find_one({"_id": teacher_username})
    if not teacher:
        raise HTTPException(status_code=401, detail="Authentication required")

    existing = announcements_collection.find_one({"_id": announcement_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Announcement not found")

    result = announcements_collection.delete_one({"_id": announcement_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=500, detail="Failed to delete announcement")

    return {"message": "Announcement deleted", "id": announcement_id}
