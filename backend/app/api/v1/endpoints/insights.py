from fastapi import APIRouter
router = APIRouter()
# Insights endpoint — served via analyses/:id
@router.get("")
async def list_insights():
    return []
