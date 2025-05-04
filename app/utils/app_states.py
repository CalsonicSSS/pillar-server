from fastapi import Request
import httpx
from supabase._async.client import AsyncClient


# The app instance is not globally accessible in route handlers
# and its bad to import it directly in other modules. which is strongly discouraged.
# to access the app state from app, we always use "request.app" gives you a safe reference to the current running FastAPI app instance
async def get_async_httpx_client(request: Request) -> httpx.AsyncClient:
    return request.app.state.httpx_client


async def get_async_supabase_client(request: Request) -> AsyncClient:
    return request.app.state.supabase_client
