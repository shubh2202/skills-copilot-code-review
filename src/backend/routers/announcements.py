"""
Announcements management endpoints

Public:
- GET /announcements -> active announcements (start_date optional, expiration_date required)

Management (requires `teacher_username` query param for simple auth):
- GET /announcements/all?teacher_username=... -> all announcements
- POST /announcements -> create announcement
- PUT /announcements/{id} -> update announcement
- DELETE /announcements/{id} -> delete announcement

"""
from fastapi import APIRouter, HTTPException, Query
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from bson import ObjectId

from ..database import announcements_collection, teachers_collection

router = APIRouter(
    prefix="/announcements",
    tags=["announcements"]
)


def _ensure_teacher(username: Optional[str]):
    if not username:
        raise HTTPException(status_code=401, detail="Authentication required")
    teacher = teachers_collection.find_one({"_id": username})
    if not teacher:
        raise HTTPException(status_code=401, detail="Invalid teacher credentials")
    return teacher


def _serialize(doc: Dict[str, Any]) -> Dict[str, Any]:
    d = {k: v for k, v in doc.items() if k != "_id"}
    d["id"] = str(doc.get("_id"))
    return d


@router.get("", response_model=List[Dict[str, Any]])
def get_active_announcements() -> List[Dict[str, Any]]:
    """Return announcements that are currently active (not expired and started)

    - An announcement is active when expiration_date >= now and (start_date is None or start_date <= now)
    Dates are stored as ISO strings.
    """
    now = datetime.now(timezone.utc)
    results = []

    # Iterate and filter, collect with parsed expiration for sorting
    tmp = []
    for a in announcements_collection.find({}):
        exp = a.get("expiration_date")
        start = a.get("start_date")
        try:
            exp_dt = datetime.fromisoformat(exp) if exp else None
        except Exception:
            exp_dt = None

        try:
            start_dt = datetime.fromisoformat(start) if start else None
        except Exception:
            start_dt = None

        if exp_dt and exp_dt >= now and (start_dt is None or start_dt <= now):
            tmp.append((exp_dt, a))

    # Sort by expiration (soonest first). If equal, preserve insertion order.
    tmp.sort(key=lambda t: t[0])
    for _, a in tmp:
        results.append(_serialize(a))

    return results


@router.get("/all", response_model=List[Dict[str, Any]])
def get_all_announcements(teacher_username: Optional[str] = Query(None)) -> List[Dict[str, Any]]:
    """Return all announcements for management view (requires teacher auth), sorted by expiration date (soonest first)"""
    _ensure_teacher(teacher_username)
    # Collect announcements with parsed expiration date for sorting
    tmp = []
    for a in announcements_collection.find({}):
        try:
            exp = datetime.fromisoformat(a.get("expiration_date"))
        except Exception:
            exp = datetime.max
        tmp.append((exp, a))
    tmp.sort(key=lambda t: t[0])
    results = [_serialize(a) for _, a in tmp]
    return results


@router.post("")
def create_announcement(title: str, message: str, expiration_date: str, start_date: Optional[str] = None, teacher_username: Optional[str] = Query(None)):
    """Create a new announcement (requires teacher authentication)

    - `expiration_date` must be an ISO date/time string.
    - `start_date` optional ISO string.
    """
    _ensure_teacher(teacher_username)
    if not expiration_date:
        raise HTTPException(status_code=400, detail="expiration_date is required")
    try:
        # validate format
        datetime.fromisoformat(expiration_date)
        if start_date:
            datetime.fromisoformat(start_date)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid date format. Use ISO format (YYYY-MM-DD or full ISO)")

    doc = {
        "title": title,
        "message": message,
        "start_date": start_date,
        "expiration_date": expiration_date,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    res = announcements_collection.insert_one(doc)
    return {"id": str(res.inserted_id), **doc}


@router.put("/{id}")
def update_announcement(id: str, title: Optional[str] = None, message: Optional[str] = None, expiration_date: Optional[str] = None, start_date: Optional[str] = None, teacher_username: Optional[str] = Query(None)):
    _ensure_teacher(teacher_username)
    try:
        oid = ObjectId(id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid id")

    update = {}
    if title is not None:
        update["title"] = title
    if message is not None:
        update["message"] = message
    if expiration_date is not None:
        try:
            datetime.fromisoformat(expiration_date)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid expiration_date format")
        update["expiration_date"] = expiration_date
    if start_date is not None:
        try:
            datetime.fromisoformat(start_date)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid start_date format")
        update["start_date"] = start_date

    if not update:
        raise HTTPException(status_code=400, detail="No fields to update")

    result = announcements_collection.update_one({"_id": oid}, {"$set": update})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Announcement not found")

    updated = announcements_collection.find_one({"_id": oid})
    return _serialize(updated)


@router.delete("/{id}")
def delete_announcement(id: str, teacher_username: Optional[str] = Query(None)):
    _ensure_teacher(teacher_username)
    try:
        oid = ObjectId(id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid id")

    result = announcements_collection.delete_one({"_id": oid})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Announcement not found")
    return {"message": "Deleted"}
