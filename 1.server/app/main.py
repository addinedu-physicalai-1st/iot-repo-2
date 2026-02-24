import asyncio
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .db import init_db
from .routers import devices, parking
from .udp_listener import run_udp_server


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("smart-parking-server")


app = FastAPI(title="Smart Parking Management Server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def on_startup() -> None:
    logger.info("Initializing database...")
    init_db()
    logger.info("Database initialized.")

    logger.info("Starting UDP listener in background...")
    asyncio.create_task(run_udp_server())


@app.get("/health")
async def health():
    return {"status": "ok"}


app.include_router(devices.router)
app.include_router(parking.router)

