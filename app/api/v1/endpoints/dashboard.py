from fastapi import APIRouter

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

@router.get("/stats")
def get_stats():
    return {"visitors": 1234, "sales": 5678}

@router.get("/reports")
def get_reports():
    return {"reports": ["report1", "report2"]}
