from fastapi import APIRouter

router = APIRouter()
# Exports endpoint — full implementation in Phase 2
@router.get("")
async def list_exports():
    return []
