from fastapi import APIRouter, Depends, Body, Request
from app.services.user_services import manage_user_from_clerk
from supabase._async.client import AsyncClient
from app.utils.app_states import get_async_supabase_client

# Webhook mostly uses the POST method when delivering webhook events. This is a standard across most webhook providers (including Clerk).
clerk_router = APIRouter(prefix="/clerk", tags=["clerk"])


# webhook request sent from Clerk to create a new corresponding user in Supabase
@clerk_router.post("/users", response_model=dict)
async def manage_user_from_clerk_handler(
    request: Request,
    supabase: AsyncClient = Depends(get_async_supabase_client),
):
    print("clerk/webhooks/users route reached")
    # this manager user is to either create or delete a user in Supabase based on the event type from Clerk triggered by the webhook
    return await manage_user_from_clerk(request, supabase)
