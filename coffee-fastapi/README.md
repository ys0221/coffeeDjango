# coffee-fastapi

`coffee/`(Spring Boot) 백엔드를 FastAPI로 다시 만들고, Claude Tool Use 기반 `/chat` 엔드포인트를 붙인 버전입니다.

## 실행

```bash
cd coffee-fastapi
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...      # /chat 에만 필요
uvicorn app.main:app --reload
```

- Swagger: http://localhost:8000/docs (SpringDoc 대응, 자동 생성)
- 최초 실행 시 SQLite(`coffee.db`)에 원두 4종이 시드됩니다. `DATABASE_URL`로 MySQL 등으로 변경 가능.
- 테스트: `pytest -q` (Claude는 가짜 클라이언트로 대체 → API 키 불필요)

## 1. Spring → FastAPI 대응표

| Spring | FastAPI (이 프로젝트) |
|---|---|
| `@RestController`, `@GetMapping` | `APIRouter`, `@router.get` — `app/routers/*.py` |
| DTO / record ReqBody / `@Valid` | Pydantic 모델 + `Field(ge=0, min_length=2)` — `app/schemas.py` |
| `RsData<T>` | `RsData[T]` (Generic Pydantic 모델) |
| JPA `@Entity` | SQLAlchemy `Mapped[...]` 모델 — `app/models.py` |
| `JpaRepository`, `EntityManager` | `Session` + `select(...)` — `app/database.py` |
| `@Service` | 그냥 함수 모음 — `app/services/*.py` |
| `@RequiredArgsConstructor` DI | `Depends(get_db)` |
| `@Transactional` | 요청당 세션 + 서비스 함수 끝에서 `commit()`, 실패 시 `rollback()` |
| `@RestControllerAdvice` | `@app.exception_handler(...)` — `app/main.py` |

### API

| Method | Path | 설명 |
|---|---|---|
| GET | `/products` | 상품 목록 |
| GET | `/products/{id}` | 상품 단건 |
| POST/PUT/DELETE | `/products[/{id}]` | 상품 생성/수정/삭제 |
| POST | `/orders` | 주문 `{customer_email, items:[{product_id, quantity}]}` |
| GET | `/orders/{email}` | 고객 주문 목록 |
| PUT | `/orders/{order_id}` | 수량/상태 수정 (재고 증감) |
| DELETE | `/orders/{email}` | 고객 주문 전체 취소 (재고 복구) |
| POST | `/chat` | Claude 주문 도우미 |

Spring 버전과 달라진 점:
- 주문 요청에서 이메일을 항목마다 반복하지 않고 바깥으로 뺐습니다.
- 주문 항목 중 하나라도 재고가 부족하면 **전체 롤백**합니다. (Spring 버전은 주문 row를 먼저 저장한 뒤 재고를 확인)
- JWT 인증/관리자 체크, Redis 장바구니, 배치·탈퇴 스케줄러는 이번 범위에서 제외했습니다.

## 2. Claude Tool Use (`/chat`)

서비스 함수 3개를 Tool로 등록했습니다 — `app/chat/tools.py`

| Tool | 연결된 서비스 함수 |
|---|---|
| `search_products(keyword, max_price, in_stock_only)` | `product_service.search` |
| `create_order(customer_email, items)` | `order_service.create_order` |
| `get_orders(customer_email)` | `order_service.find_all_by_customer_email` |

루프(`app/chat/agent.py`):
1. 사용자 메시지 + Tool 정의를 Claude에 보냄
2. `stop_reason == "tool_use"` → `tool_use` 블록들을 실행해 `tool_result`로 묶어 다시 보냄
3. Claude가 Tool을 더 이상 호출하지 않으면 최종 답변 반환

```bash
curl -X POST localhost:8000/chat -H 'content-type: application/json' \
  -d '{"message": "7000원 이하 원두 추천해줘"}'
```

응답에는 `reply`와 함께 어떤 Tool이 어떤 입력으로 호출됐는지(`tool_calls`)가 들어있습니다.
서버는 대화 상태를 저장하지 않으므로, 이어지는 대화는 이전 텍스트를 `history`로 넘겨주세요:

```json
{"message": "네 2개 주문해주세요. a@test.com 이에요",
 "history": [{"role": "user", "content": "7000원 이하 원두 추천해줘"},
             {"role": "assistant", "content": "Columbia Nariño(5000원)를 추천해요..."}]}
```

설정(환경변수): `CLAUDE_MODEL`(기본 `claude-opus-5-5`), `CLAUDE_EFFORT`(기본 `low`).
- 시스템 프롬프트로 **주문 전 고객 확인**을 요구합니다 (`create_order`는 실제 재고를 차감).
- Tool 에러(재고 부족, 없는 상품)는 `is_error: true`로 Claude에게 돌려줘서 Claude가 사용자에게 설명합니다.
- 안전 분류기가 요청을 거절하면 서버 측에서 대체 모델로 다시 시도합니다(`fallbacks="default"`).
