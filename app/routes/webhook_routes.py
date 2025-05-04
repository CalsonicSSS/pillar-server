from fastapi import APIRouter, Depends, Body, Request
from app.services.user_services import manage_user_from_clerk
from supabase._async.client import AsyncClient
from app.utils.app_states import get_async_supabase_client

# Webhook mostly uses the POST method when delivering webhook events. This is a standard across most webhook providers (including Clerk).
webhook_router = APIRouter(prefix="/webhooks", tags=["webhooks"])


# webhook request sent from Clerk to create a new corresponding user in Supabase
@webhook_router.post("/clerk/users", response_model=dict)
async def manage_user_from_clerk_handler(
    request: Request,
    supabase: AsyncClient = Depends(get_async_supabase_client),
):
    print("/webhooks/clerk/users route reached")
    return await manage_user_from_clerk(request, supabase)
