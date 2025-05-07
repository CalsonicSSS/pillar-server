from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import httpx
from contextlib import asynccontextmanager
from app.core.config import app_config_settings
from supabase._async.client import create_client
from app.routes.project_routes import project_router
from app.routes.webhook_routes import webhook_router
from app.routes.channel_routes import channel_router
from app.routes.oauth_gmail_routes import oauth_router
from app.routes.message_routes import message_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize Supabase client and store it in app state
    print("Fastapi Start-up Setting...")
    app.state.supabase_client = await create_client(app_config_settings.SUPABASE_URL, app_config_settings.SUPABASE_KEY)
    app.state.httpx_client = httpx.AsyncClient()
    yield
    # Shutdown: Clean up resources if necessary
    print("shutting down cleaning...")
    await app.state.httpx_client.aclose()
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
app.include_router(oauth_router, prefix=app_config_settings.API_V1_PREFIX)
app.include_router(message_router, prefix=app_config_settings.API_V1_PREFIX)


@app.get("/")
async def root():
    return {"message": "Welcome to Pillar API"}


@app.get(f"{app_config_settings.API_V1_PREFIX}/health")
async def health_check():
    return {"status": "healthy"}
