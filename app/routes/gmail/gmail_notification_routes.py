from fastapi import APIRouter, Request, Depends
from app.utils.app_states import get_async_supabase_client
from app.services.gmail.gmail_notification_services import process_gmail_pub_sub_notifications
from supabase._async.client import AsyncClient

# Create a router for Gmail notifications
notification_router = APIRouter(prefix="/gmail/notifications", tags=["gmail-notifications"])


@notification_router.post("/pub-sub")
async def process_gmail_pub_sub_notifications_handler(
    request: Request,
    supabase: AsyncClient = Depends(get_async_supabase_client),
):
    """
    Handle Gmail notifications sent by Google Pub/Sub.

    This endpoint receives notifications when changes occur in
    monitored Gmail accounts. Each notification contains
    information about the change but not the actual email content.
    """
    print("/gmail/notifications/pub-sub POST route reached")
    return await process_gmail_pub_sub_notifications(request, supabase)
