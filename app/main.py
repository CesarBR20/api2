from fastapi import FastAPI
from app.api.routes import router as api_router
from dotenv import load_dotenv
from app.config_loader import load_config
import logging

app = FastAPI(title="SAT CFDI API")

@app.get("/health")
async def health():
    return {"status": "ok"}

config = load_config()

load_dotenv()

for route in app.routes:
    logging.warning(f"Route: {route.path}")

app.include_router(api_router)
