"""1단계 서비스 함수를 Claude Tool로 노출.

구성
- TOOLS          : Claude에게 보내는 Tool 정의(JSON Schema). strict=True로 입력 스키마를 보장.
- run_tool()     : Claude가 고른 Tool 이름/입력을 실제 서비스 함수 호출로 연결(디스패처).

Tool 결과는 JSON 문자열로 돌려줍니다. 에러는 예외를 던지지 않고 (내용, is_error=True)로
돌려줘서 Claude가 사용자에게 상황을 설명하거나 다른 방법을 시도할 수 있게 합니다.
"""
import json
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.schemas import OrderDto, ProductDto
from app.services import order_service, product_service
from app.services.errors import BusinessError, NotFoundError

TOOLS: list[dict[str, Any]] = [
    {
        "name": "search_products",
        "description": (
            "카페에서 판매하는 원두 상품을 검색합니다. 상품명 키워드, 최대 가격, 재고 여부로 필터링할 수 있고 "
            "id/이름/가격(원)/재고를 돌려줍니다. 사용자가 원두를 추천받거나 가격·재고를 묻거나, "
            "주문 전에 product_id를 알아내야 할 때 사용하세요. 필터를 모두 null로 두면 전체 목록을 반환합니다."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "keyword": {
                    "type": ["string", "null"],
                    "description": "상품명에 포함될 키워드 (예: '에티오피아', 'Colombia'). 없으면 null.",
                },
                "max_price": {
                    "type": ["integer", "null"],
                    "description": "최대 가격(원). 없으면 null.",
                },
                "in_stock_only": {
                    "type": "boolean",
                    "description": "true면 재고가 있는 상품만 반환.",
                },
            },
            "required": ["keyword", "max_price", "in_stock_only"],
            "additionalProperties": False,
        },
    },
    {
        "name": "create_order",
        "description": (
            "고객 이메일로 원두 주문을 생성하고 재고를 차감합니다. 여러 상품을 한 번에 주문할 수 있으며, "
            "하나라도 실패(상품 없음, 재고 부족)하면 전체 주문이 취소됩니다. "
            "실제 주문이 발생하는 작업이므로 반드시 사용자에게 상품·수량·총액을 확인받은 뒤에만 호출하세요. "
            "product_id는 search_products 결과에서 가져와야 합니다."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "customer_email": {"type": "string", "description": "주문하는 고객의 이메일"},
                "items": {
                    "type": "array",
                    "description": "주문 항목 목록",
                    "items": {
                        "type": "object",
                        "properties": {
                            "product_id": {"type": "integer", "description": "상품 id"},
                            "quantity": {"type": "integer", "description": "수량 (1 이상)"},
                        },
                        "required": ["product_id", "quantity"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["customer_email", "items"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_orders",
        "description": (
            "고객 이메일로 지금까지의 주문 목록(상품, 수량, 주문 시각, 처리 상태)을 조회합니다. "
            "사용자가 내 주문 내역이나 배송 상태를 물을 때, 또는 주문 직후 결과를 확인할 때 사용하세요."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "customer_email": {"type": "string", "description": "조회할 고객의 이메일"},
            },
            "required": ["customer_email"],
            "additionalProperties": False,
        },
    },
]


# ---------- Tool 구현: 서비스 함수 호출 → JSON 직렬화 가능한 dict ----------
def _search_products(db: Session, keyword: str | None, max_price: int | None, in_stock_only: bool) -> dict:
    products = product_service.search(db, keyword=keyword, max_price=max_price, in_stock_only=in_stock_only)
    return {"count": len(products), "products": [ProductDto.model_validate(p).model_dump() for p in products]}


def _create_order(db: Session, customer_email: str, items: list[dict]) -> dict:
    orders = order_service.create_order(db, customer_email, [(i["product_id"], i["quantity"]) for i in items])
    total = sum(o.product.price * o.quantity for o in orders)
    return {
        "message": order_service.delivery_message(orders[0].order_date, "주문"),
        "total_price": total,
        "orders": [OrderDto.model_validate(o).model_dump(mode="json") for o in orders],
    }


def _get_orders(db: Session, customer_email: str) -> dict:
    orders = order_service.find_all_by_customer_email(db, customer_email)
    return {"count": len(orders), "orders": [OrderDto.model_validate(o).model_dump(mode="json") for o in orders]}


_HANDLERS: dict[str, Callable[..., dict]] = {
    "search_products": _search_products,
    "create_order": _create_order,
    "get_orders": _get_orders,
}


def run_tool(db: Session, name: str, tool_input: dict[str, Any]) -> tuple[str, bool]:
    """Tool 실행. (결과 JSON 문자열, is_error) 를 반환."""
    handler = _HANDLERS.get(name)
    if handler is None:
        return json.dumps({"error": f"알 수 없는 tool: {name}"}, ensure_ascii=False), True
    try:
        result = handler(db, **tool_input)
        return json.dumps(result, ensure_ascii=False), False
    except (NotFoundError, BusinessError) as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False), True
    except TypeError as e:  # 스키마와 맞지 않는 입력
        return json.dumps({"error": f"잘못된 입력: {e}"}, ensure_ascii=False), True
