from fastapi import APIRouter

from app.api.routers import auth, past_products, products, runs, system

api_router = APIRouter()
api_router.include_router(system.router)
api_router.include_router(auth.router)
api_router.include_router(products.router)
api_router.include_router(past_products.router)
api_router.include_router(runs.router)
