"""ProductService.java 대응 — @Service는 그냥 함수 모음이면 충분합니다.

트랜잭션: 읽기 함수는 commit 없이, 쓰기 함수는 마지막에 db.commit().
(@Transactional(readOnly = true) / @Transactional 구분과 같은 감각)
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Product
from app.services.errors import NotFoundError


def find_all(db: Session) -> list[Product]:
    # Spring 컨트롤러의 .reversed() 처럼 최신 상품 먼저
    return list(db.scalars(select(Product).order_by(Product.id.desc())))


def find_by_id(db: Session, product_id: int) -> Product:
    product = db.get(Product, product_id)
    if product is None:
        raise NotFoundError(f"{product_id}번 상품을 찾을 수 없습니다.")
    return product


def search(
    db: Session,
    keyword: str | None = None,
    max_price: int | None = None,
    in_stock_only: bool = False,
) -> list[Product]:
    """원두 검색 — Claude Tool로도 쓰이는 함수."""
    stmt = select(Product)
    if keyword:
        stmt = stmt.where(Product.name.ilike(f"%{keyword}%"))
    if max_price is not None:
        stmt = stmt.where(Product.price <= max_price)
    if in_stock_only:
        stmt = stmt.where(Product.stock > 0)
    return list(db.scalars(stmt.order_by(Product.price)))


def create(db: Session, name: str, price: int, stock: int, image_url: str | None) -> Product:
    product = Product(name=name, price=price, stock=stock, image_url=image_url)
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


def modify(db: Session, product: Product, name: str, price: int, stock: int, image_url: str | None) -> Product:
    # JPA의 dirty checking 대신 속성 변경 후 commit
    product.name, product.price, product.stock, product.image_url = name, price, stock, image_url
    db.commit()
    return product


def delete(db: Session, product: Product) -> None:
    db.delete(product)
    db.commit()
