"""SQLAlchemy 모델 — Spring의 JPA @Entity 대응."""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Product(Base):
    __tablename__ = "product"

    id: Mapped[int] = mapped_column("product_id", Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    price: Mapped[int] = mapped_column(Integer, nullable=False)
    stock: Mapped[int] = mapped_column(Integer, nullable=False)
    image_url: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Product.decreaseStock / increaseStock 그대로
    def decrease_stock(self, quantity: int) -> None:
        if self.stock < quantity:
            raise ValueError("재고가 부족합니다.")
        self.stock -= quantity

    def increase_stock(self, quantity: int) -> None:
        if quantity < 0:
            raise ValueError("재고 증가 수량은 0보다 작을 수 없습니다.")
        self.stock += quantity


class Order(Base):
    __tablename__ = "orders"  # `order`는 예약어라 Spring에선 백틱으로 감쌌던 부분

    order_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("product.product_id"), nullable=False)
    order_date: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)
    order_state: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)

    # @ManyToOne(fetch = LAZY) 대응
    product: Mapped[Product] = relationship(lazy="joined")
