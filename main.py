import logging

from contextlib import asynccontextmanager
from fastapi import FastAPI

from app.core.clients import (
    create_service_clients,
    close_service_clients,
)
from app.core.startup_checks import run_startup_checks
from app.api.v1.router import api_router
from app.middleware.correlation_id import correlation_id_middleware
from app.middleware.exception_handlers import register_exception_handlers
from app.middleware.exception_handlers import *
from app.persistence.database import *



logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):

    logger.info("Starting Danube Chatbot Backend")

    # Step 1: Create external service clients
    clients = await create_service_clients()

    app.state.clients = clients

    try:
        # Step 2: Verify connectivity
        startup_status = await run_startup_checks(clients)

        logger.info("Startup checks: %s", startup_status)

        # Step 3: Check mandatory dependencies
        if not all(
            status == "healthy"
            for status in startup_status.values()
        ):
            raise RuntimeError(
                "Application startup failed: "
                "One or more dependencies are unhealthy"
            )

        logger.info("Application startup completed")

        # Step 4: Application starts serving requests
        yield

    finally:
        # Step 5: Close connections during shutdown
        await close_service_clients(clients)

        logger.info("Application shutdown completed")


app = FastAPI(
    title="Danube Chatbot Backend",
    version="1.0.0",
    lifespan=lifespan,
)

app.middleware("http")(correlation_id_middleware)

register_exception_handlers(app)

app.include_router(
    api_router,
    prefix="/api/v1",
)
