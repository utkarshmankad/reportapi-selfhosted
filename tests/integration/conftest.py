import pytest_asyncio
from app.db.session import engine


@pytest_asyncio.fixture(autouse=True)
async def _dispose_engine_per_test():
    """
    pytest-asyncio gives each test function its own event loop; asyncpg
    connections are bound to the loop that created them. Disposing the
    shared engine's pool after every test forces a fresh connection on
    the next test's loop instead of reusing one tied to a closed loop.
    """
    yield
    await engine.dispose()
