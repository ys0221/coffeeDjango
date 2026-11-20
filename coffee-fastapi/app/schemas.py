"""Pydantic 모델 — Spring의 DTO / record ReqBody / RsData 대응.

@Valid + @NotBlank/@Min 같은 검증은 Field(...) 제약으로 표현합니다.
"""
from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class RsData(BaseModel, Generic[T]):
    """global/rsData/RsData.java"""
    resultCode: str
    msg: str
    data: T | None = None


# ---------- Product ----------
class ProductDto(BaseModel):
    model_config = ConfigDict(from_attributes=True)  # ProductDto(Product p) 생성자 역할

    id: int
    name: str
    price: int
    stock: int
    image_url: str | None = None


class ProductWriteReq(BaseModel):
    """ProductWriteReqBody / ProductModifyReqBody"""
    name: str = Field(min_length=2, max_length=50)
    price: int = Field(ge=0)
    stock: int = Field(ge=0)
    image_url: str | None = None


# ---------- Order ----------
class OrderItemReq(BaseModel):
    product_id: int
    quantity: int = Field(ge=1, description="수량은 1 이상이어야 합니다.")


class OrderCreateReq(BaseModel):
    """POST /orders 요청. Spring에선 List<OrderDto>에 이메일이 매 항목마다 반복됐는데,
    한 번의 주문 = 한 고객이므로 이메일을 바깥으로 뺐습니다."""
    customer_email: str = Field(min_length=3)
    items: list[OrderItemReq] = Field(min_length=1)


class OrderUpdateReq(BaseModel):
    quantity: int | None = Field(default=None, ge=1)
    order_state: bool | None = None


class OrderDto(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    order_id: int
    customer_email: str
    product_id: int
    order_date: datetime
    order_state: bool
    quantity: int
    product: ProductDto | None = None


# ---------- Chat ----------
class ChatMessage(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str


class ChatReq(BaseModel):
    message: str = Field(min_length=1)
    history: list[ChatMessage] = Field(default_factory=list, description="이전 대화(텍스트만)")


class ToolCallLog(BaseModel):
    name: str
    input: dict
    output: str
    is_error: bool = False


class ChatRes(BaseModel):
    reply: str
    tool_calls: list[ToolCallLog]
