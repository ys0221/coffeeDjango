"""CoffeeApplication.java 대응 — 앱 생성, 라우터 등록, 전역 예외 처리, 초기 데이터."""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app.database import Base, SessionLocal, engine
from app.models import Product
from app.routers import chat, orders, products
from app.services.errors import BusinessError, NotFoundError

SEED_PRODUCTS = [
    ("Columbia Nariño", 5000, 100),
    ("Brazil Serra Do Caparaó", 6000, 100),
    ("Columbia Quindío (White Wine Extended Fermentation)", 7000, 100),
    ("Ethiopia Sidamo", 8000, 100),
]


def seed() -> None:
    with SessionLocal() as db:
        if db.scalar(select(Product).limit(1)) is None:
            db.add_all(Product(name=n, price=p, stock=s) for n, p, s in SEED_PRODUCTS)
            db.commit()


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(engine)  # ddl-auto: update 비슷한 역할(테이블 없으면 생성)
    seed()
    yield


app = FastAPI(title="Grids & Circles Coffee API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # coffee-front (Next.js)
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(products.router)
app.include_router(orders.router)
app.include_router(chat.router)


# GlobalExceptionHandler.java 대응 (@RestControllerAdvice)
@app.exception_handler(NotFoundError)
async def handle_not_found(_: Request, e: NotFoundError):
    return JSONResponse(status_code=404, content={"resultCode": "404-1", "msg": str(e), "data": None})


@app.exception_handler(BusinessError)
async def handle_business(_: Request, e: BusinessError):
    return JSONResponse(status_code=400, content={"resultCode": "400-1", "msg": str(e), "data": None})
