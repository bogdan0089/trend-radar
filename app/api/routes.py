from fastapi import APIRouter

from app.api.routers import auth, products, sales_boost, scrape_runs, system

api_router = APIRouter()
api_router.include_router(system.router_system)
api_router.include_router(auth.router_auth)
api_router.include_router(products.router_products)
api_router.include_router(sales_boost.router_sales_boost)
api_router.include_router(scrape_runs.router_scrape_runs)
