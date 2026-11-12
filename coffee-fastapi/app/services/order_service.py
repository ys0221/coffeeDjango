"""OrderService.java 대응."""
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Order, Product
from app.services.errors import BusinessError, NotFoundError

CUTOFF_HOUR = 14  # 오후 2시 기준 배송 정책


def delivery_message(order_time: datetime, action: str = "주문") -> str:
    if order_time.hour >= CUTOFF_HOUR:
        return "당일 오후 2시 이후의 주문 건은 다음 날 배송이 시작됩니다."
    return f"{action}이 완료되었습니다. 배송은 금일 시작됩니다."


def create_order(db: Session, customer_email: str, items: list[tuple[int, int]]) -> list[Order]:
    """주문 생성 — Claude Tool로도 쓰이는 함수.

    items: [(product_id, quantity), ...]
    하나라도 실패하면 전체 롤백 (하나의 @Transactional 안에서 처리한 것과 동일).
    """
    if not items:
        raise BusinessError("주문 항목이 비어 있습니다.")
    now = datetime.now()
    orders: list[Order] = []
    try:
        for product_id, quantity in items:
            if quantity < 1:
                raise BusinessError("수량은 1 이상이어야 합니다.")
            product = db.get(Product, product_id)
            if product is None:
                raise NotFoundError(f"{product_id}번 상품을 찾을 수 없습니다.")
            try:
                product.decrease_stock(quantity)
            except ValueError as e:
                raise BusinessError(f"{product.name}: {e} (남은 재고 {product.stock}개)") from e
            order = Order(
                customer_email=customer_email,
                product_id=product_id,
                order_date=now,
                order_state=False,
                quantity=quantity,
            )
            db.add(order)
            orders.append(order)
        db.commit()
    except Exception:
        db.rollback()
        raise
    for o in orders:
        db.refresh(o)
    return orders


def find_all_by_customer_email(db: Session, customer_email: str) -> list[Order]:
    """주문 조회 — Claude Tool로도 쓰이는 함수."""
    stmt = select(Order).where(Order.customer_email == customer_email).order_by(Order.order_date.desc())
    return list(db.scalars(stmt))


def update_order(db: Session, order_id: int, quantity: int | None, order_state: bool | None) -> Order:
    order = db.get(Order, order_id)
    if order is None:
        raise NotFoundError("주문을 찾을 수 없습니다")
    try:
        if quantity is not None and quantity != order.quantity:
            product = db.get(Product, order.product_id)
            diff = quantity - order.quantity
            try:
                if diff > 0:
                    product.decrease_stock(diff)
                else:
                    product.increase_stock(-diff)
            except ValueError as e:
                raise BusinessError(str(e)) from e
            order.quantity = quantity
            order.order_date = datetime.now()
        if order_state is not None:
            order.order_state = order_state
            order.order_date = datetime.now()
        db.commit()
    except Exception:
        db.rollback()
        raise
    return order


def delete_by_customer_email(db: Session, customer_email: str) -> int:
    orders = find_all_by_customer_email(db, customer_email)
    for order in orders:
        product = db.get(Product, order.product_id)
        if product is not None:
            product.increase_stock(order.quantity)
        db.delete(order)
    db.commit()
    return len(orders)
