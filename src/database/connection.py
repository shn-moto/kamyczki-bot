from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import text

from src.config import settings
from src.database.models import Base

engine = create_async_engine(settings.db_url, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_session() -> AsyncSession:
    async with async_session() as session:
        yield session


async def init_db():
    """Initialize database, create tables and indexes."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        # Create HNSW index for fast vector similarity search
        # This index dramatically speeds up cosine similarity queries
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS stones_embedding_hnsw_idx
            ON stones
            USING hnsw (embedding vector_cosine_ops)
            WITH (m = 16, ef_construction = 64)
        """))
