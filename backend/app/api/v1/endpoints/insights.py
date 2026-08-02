"""
Insights endpoint — unused placeholder.

Real insights are nested inside `GET /analyses/{id}` (see
`AnalysisDetailResponse.insights` in `app/api/v1/endpoints/analyses.py`),
not served from a standalone `/insights` route. This route returns an
empty list unconditionally and is not called by the frontend; kept for API
surface compatibility rather than removed, since deleting a route is a
behavior change some caller could depend on.
"""

from fastapi import APIRouter

router = APIRouter()


@router.get("")
async def list_insights() -> list:
    return []
