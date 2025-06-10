from fastapi import FastAPI
from app.api.routes import router as api_router
from dotenv import load_dotenv

app = FastAPI(title="SAT CFDI API")

load_dotenv()

app.include_router(api_router)
