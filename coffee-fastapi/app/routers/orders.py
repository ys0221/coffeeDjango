"""OrderController.java 대응."""
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import OrderCreateReq, OrderDto, OrderUpdateReq, RsData
from app.services import order_service

router = APIRouter(prefix="/orders", tags=["주문 API"])


@router.post("", response_model=RsData[list[OrderDto]], status_code=status.HTTP_201_CREATED, summary="주문")
def create_order(req: OrderCreateReq, db: Session = Depends(get_db)):
    orders = order_service.create_order(db, req.customer_email, [(i.product_id, i.quantity) for i in req.items])
    msg = order_service.delivery_message(orders[0].order_date, "주문")
    return RsData(resultCode="201-1", msg=msg, data=[OrderDto.model_validate(o) for o in orders])


@router.get("/{customer_email}", response_model=RsData[list[OrderDto]], summary="특정 고객의 주문 목록 조회")
def get_orders(customer_email: str, db: Session = Depends(get_db)):
    orders = order_service.find_all_by_customer_email(db, customer_email)
    return RsData(resultCode="200-1", msg="주문 상세 정보를 조회했습니다.", data=[OrderDto.model_validate(o) for o in orders])


@router.put("/{order_id}", response_model=RsData[OrderDto], summary="주문 수정")
def update_order(order_id: int, req: OrderUpdateReq, db: Session = Depends(get_db)):
    order = order_service.update_order(db, order_id, req.quantity, req.order_state)
    msg = order_service.delivery_message(order.order_date, "수정")
    return RsData(resultCode="200-1", msg=msg, data=OrderDto.model_validate(order))


@router.delete("/{customer_email}", response_model=RsData[None], summary="주문 취소")
def cancel_orders(customer_email: str, db: Session = Depends(get_db)):
    order_service.delete_by_customer_email(db, customer_email)
    return RsData(resultCode="200-1", msg="주문이 취소되었습니다.")
