from fastapi import APIRouter

from app.api.routers import auth, products, system

api_router = APIRouter()
api_router.include_router(system.router)
api_router.include_router(auth.router)
api_router.include_router(products.router)
