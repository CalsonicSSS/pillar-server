from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import httpx
from contextlib import asynccontextmanager
from app.core.config import app_config_settings
from supabase._async.client import create_client
from app.routes.project_routes import project_router
from app.routes.webhook_routes import webhook_router
from app.routes.channel_routes import channel_router
from app.routes.gmail.gmail_oauth_channel_routes import oauth_router
from app.routes.gmail.gmail_msg_routes import message_router
from app.routes.contact_routes import contact_router
from app.routes.timeline_recap_routes import timeline_recap_router
from app.utils.scheduler import init_scheduler, shutdown_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize Supabase client and store it in app state
    print("Fastapi Start-up Setting...")
    app.state.supabase_client = await create_client(app_config_settings.SUPABASE_URL, app_config_settings.SUPABASE_KEY)
    app.state.httpx_client = httpx.AsyncClient()

    # Initialize scheduler
    init_scheduler(app.state.supabase_client)
    print("Fastapi Start-up completed!")

    yield

    # Shutdown: Clean up resources if necessary
    print("shutting down cleaning...")
    await app.state.httpx_client.aclose()

    # Shutdown scheduler
    shutdown_scheduler()

    print("cleaning done and closed")


app = FastAPI(
    title=app_config_settings.PROJECT_NAME,
    openapi_url=f"{app_config_settings.API_V1_PREFIX}/openapi.json",
    docs_url=f"{app_config_settings.API_V1_PREFIX}/docs",
    redoc_url=f"{app_config_settings.API_V1_PREFIX}/redoc",
    debug=app_config_settings.DEBUG,
    lifespan=lifespan,  # Pass the lifespan function here
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust this in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(project_router, prefix=app_config_settings.API_V1_PREFIX)
app.include_router(webhook_router, prefix=app_config_settings.API_V1_PREFIX)
app.include_router(channel_router, prefix=app_config_settings.API_V1_PREFIX)
app.include_router(contact_router, prefix=app_config_settings.API_V1_PREFIX)
app.include_router(oauth_router, prefix=app_config_settings.API_V1_PREFIX)
app.include_router(message_router, prefix=app_config_settings.API_V1_PREFIX)
app.include_router(timeline_recap_router, prefix=app_config_settings.API_V1_PREFIX)


@app.get("/")
async def root():
    return {"message": "Welcome to Pillar API"}


@app.get(f"{app_config_settings.API_V1_PREFIX}/health")
async def health_check():
    return {"status": "healthy"}
