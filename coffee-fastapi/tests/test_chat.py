"""실제 API 호출 없이 /chat 의 Tool Use 루프를 검증 (가짜 Claude 클라이언트)."""
import json
from types import SimpleNamespace as NS

from app.chat.agent import get_claude_client
from app.main import app


def text(t):
    return NS(type="text", text=t)


def tool_use(id_, name, input_):
    return NS(type="tool_use", id=id_, name=name, input=input_)


class FakeClaude:
    def __init__(self, scripted):
        self.scripted = list(scripted)
        self.requests = []
        self.beta = NS(messages=NS(create=self._create))

    def _create(self, **kwargs):
        self.requests.append(json.loads(json.dumps(kwargs["messages"], default=lambda o: o.__dict__)))
        return self.scripted.pop(0)


def use_fake(scripted):
    fake = FakeClaude(scripted)
    app.dependency_overrides[get_claude_client] = lambda: fake
    return fake


def test_chat_search_then_answer(client):
    fake = use_fake([
        NS(stop_reason="tool_use", content=[
            text("찾아볼게요."),
            tool_use("t1", "search_products", {"keyword": "Ethiopia", "max_price": None, "in_stock_only": True}),
        ]),
        NS(stop_reason="end_turn", content=[text("Ethiopia Sidamo가 8000원이에요.")]),
    ])
    r = client.post("/chat", json={"message": "에티오피아 원두 있어요?"})
    body = r.json()
    assert r.status_code == 200
    assert body["reply"] == "Ethiopia Sidamo가 8000원이에요."
    assert body["tool_calls"][0]["name"] == "search_products"
    assert json.loads(body["tool_calls"][0]["output"])["products"][0]["name"] == "Ethiopia Sidamo"

    # 두 번째 요청에 tool_result 가 user 메시지로 들어갔는지
    last = fake.requests[1][-1]
    assert last["role"] == "user" and last["content"][0]["type"] == "tool_result"
    assert last["content"][0]["tool_use_id"] == "t1"


def test_chat_create_and_get_orders(client):
    use_fake([
        NS(stop_reason="tool_use", content=[
            tool_use("t1", "create_order",
                     {"customer_email": "b@test.com", "items": [{"product_id": 4, "quantity": 2}]}),
        ]),
        NS(stop_reason="tool_use", content=[tool_use("t2", "get_orders", {"customer_email": "b@test.com"})]),
        NS(stop_reason="end_turn", content=[text("주문 완료! 총 16000원입니다.")]),
    ])
    body = client.post("/chat", json={"message": "네, 주문해주세요"}).json()
    assert [c["name"] for c in body["tool_calls"]] == ["create_order", "get_orders"]
    assert json.loads(body["tool_calls"][0]["output"])["total_price"] == 16000
    assert client.get("/products/4").json()["stock"] == 98


def test_chat_tool_error_is_returned_to_claude(client):
    fake = use_fake([
        NS(stop_reason="tool_use", content=[
            tool_use("t1", "create_order",
                     {"customer_email": "c@test.com", "items": [{"product_id": 1, "quantity": 9999}]}),
        ]),
        NS(stop_reason="end_turn", content=[text("재고가 부족해요.")]),
    ])
    body = client.post("/chat", json={"message": "9999개 주문"}).json()
    assert body["tool_calls"][0]["is_error"] is True
    assert fake.requests[1][-1]["content"][0]["is_error"] is True
