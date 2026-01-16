from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from src.config import settings
from src.database.models import Stone

router = APIRouter()

# Create separate engine for web server (different event loop)
_web_engine = None
_web_session_maker = None


def get_web_session():
    """Get async session for web server context."""
    global _web_engine, _web_session_maker
    if _web_engine is None:
        _web_engine = create_async_engine(settings.database_url, echo=False)
        _web_session_maker = async_sessionmaker(_web_engine, class_=AsyncSession, expire_on_commit=False)
    return _web_session_maker()


@router.get("/stones/{stone_id}/map-data")
async def get_stone_map_data(stone_id: int):
    """Get stone data with history points for map visualization."""
    async with get_web_session() as session:
        result = await session.execute(
            select(Stone)
            .options(selectinload(Stone.history))
            .where(Stone.id == stone_id)
        )
        stone = result.scalar_one_or_none()

        if not stone:
            raise HTTPException(status_code=404, detail="Stone not found")

        # Build points list from history (chronological order)
        points = []
        for h in sorted(stone.history, key=lambda x: x.created_at):
            if h.latitude and h.longitude:
                points.append({
                    "lat": h.latitude,
                    "lon": h.longitude,
                    "date": h.created_at.strftime("%Y-%m-%d %H:%M"),
                    "zip_code": h.zip_code,
                })

        return {
            "stone": {
                "id": stone.id,
                "name": stone.name,
                "description": stone.description,
            },
            "points": points,
        }


@router.get("/stones")
async def get_all_stones():
    """Get list of all stones with their latest location."""
    async with get_web_session() as session:
        result = await session.execute(
            select(Stone).options(selectinload(Stone.history))
        )
        stones = result.scalars().all()

        stones_list = []
        for stone in stones:
            # Get latest location from history
            latest_with_coords = None
            for h in sorted(stone.history, key=lambda x: x.created_at, reverse=True):
                if h.latitude and h.longitude:
                    latest_with_coords = h
                    break

            stones_list.append({
                "id": stone.id,
                "name": stone.name,
                "history_count": len(stone.history),
                "latest_location": {
                    "lat": latest_with_coords.latitude,
                    "lon": latest_with_coords.longitude,
                } if latest_with_coords else None,
            })

        return {"stones": stones_list}
