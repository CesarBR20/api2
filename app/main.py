from fastapi import FastAPI
from app.api.routes import router as api_router
from dotenv import load_dotenv
from app.config_loader import load_config

app = FastAPI(title="SAT CFDI API")

config = load_config()

load_dotenv()

app.include_router(api_router)
