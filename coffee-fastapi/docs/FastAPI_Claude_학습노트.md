# 데브코스 1차 프로젝트를 FastAPI로 변환하고 Claude API 호출해보기

## 1. CRUD

### Spring Boot vs FastAPI

**Spring Boot**

```java
@GetMapping("/{id}")
// @PathVariable → URL에 있는 변수 값을 꺼내서 메서드 파라미터로 받는 것
public ProductDto getItem(@PathVariable Long id) {
    Product p = productService.findById(id).get();
    return new ProductDto(p);      // ← FastAPI는 이 변환을 자동으로 해줌
}
```

**FastAPI**

```python
router = APIRouter(prefix="/products", tags=["상품 API"])
#  ↑ Spring의 @RequestMapping("/products")와 같음
#    tags는 Swagger 화면에서 묶어 보여줄 이름

@router.get("/{product_id}", response_model=ProductDto, summary="상품 단건 조회")
#  ↑ @GetMapping("/{id}")와 같음
#    response_model=ProductDto → "응답은 ProductDto 모양으로 내보내라"
#    summary → @Operation(summary=...)처럼 Swagger 설명

def get_item(product_id: int, db: Session = Depends(get_db)):
#            ↑ URL의 {product_id}와 이름이 같아서 자동으로 값이 들어옴 (@PathVariable 불필요)
#              ": int"라서 "abc"가 들어오면 FastAPI가 알아서 422 에러를 돌려줌
#                              ↑ Depends(get_db): get_db를 실행해서 세션을 넣어줌 (의존성 주입)

    return product_service.find_by_id(db, product_id)
    #  ↑ 서비스 함수 호출. Entity(Product)를 그대로 반환해도
    #    response_model 덕분에 JSON으로 바뀌어 나감
```

- `APIRouter` → 공통 URL 앞부분(prefix)을 정하고 관련된 API를 묶는다
    - `prefix="/products"` + `"/{product_id}"` = `/products/{product_id}`
- `@router.get(...)` 데코레이터(어노테이션처럼 쓰는 Python 문법)로 HTTP 메서드(GET, POST, PUT, DELETE), 응답 모델 형식, Swagger 설명을 설정한다
    - `"/{product_id}"` → URL 매칭
    - `response_model` → 응답 모델 형식
    - `summary` → Swagger 설명
- `Depends(함수 이름)` → 요청마다 그 함수를 실행해서 결과를 파라미터에 넣어준다 (의존성 주입)
    - DB 전용 기능이 아님. `get_db`를 넣었기 때문에 세션이 들어온 것
    - `/chat`에서는 `Depends(agent.get_claude_client)`로 Claude 클라이언트를 받음

### Database 연결 (database.py)

```python
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./coffee.db")   # ① 어떤 DB에 연결할지

engine = create_engine(                                              # ② DB 연결 관리자
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)   # ③ 세션 공장

class Base(DeclarativeBase):                                         # ④ 모든 테이블 클래스의 부모
    pass

def get_db():                                                        # ⑤ 요청마다 세션 빌려주기
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

**① DATABASE_URL**

- `"DATABASE_URL"` → 환경 변수에 정의되어 있는 DATABASE_URL을 읽음
- `"sqlite:///./coffee.db"` → 환경 변수가 없을 때 사용할 기본값
- 실제 DB(MySQL 등)로 바꿀 때는 코드를 고치지 않고 환경 변수만 바꾼다 → 비밀번호가 GitHub에 올라가지 않음

**② engine** → DB와의 실제 연결(커넥션 풀)을 관리하는 객체. 앱 전체에서 딱 하나만 만든다 (Spring의 `DataSource`)

- SQLite는 "연결을 만든 스레드에서만 써라"라는 규칙이 있음 → FastAPI는 요청을 여러 스레드에서 처리하므로 에러 발생 가능 → `check_same_thread: False`로 규칙을 끔
- `if DATABASE_URL.startswith("sqlite") else {}` → SQLite일 때만 이 옵션을 넣는다 (MySQL에는 이 규칙이 없음)

**③ SessionLocal** → 호출할 때마다 새로운 세션이 만들어진다 (`SessionLocal()`)

- Session = JPA의 영속성 컨텍스트(EntityManager)와 같은 역할
    - 하나의 요청에서 하는 DB 작업들을 모아서 관리하는 객체
    - 1차 캐시, 변경 감지, commit/rollback(트랜잭션)을 담당
    - DB 자체도, DB 연결도 아님. 필요할 때 커넥션 풀에서 연결을 빌려 쓰고 돌려준다
- `sessionmaker` = 세션을 만드는 공장
    - `bind=engine` → 이 세션은 engine을 통해 DB에 연결
    - `autoflush=False` → 조회(쿼리) 전에 쌓아둔 변경 사항을 DB로 자동으로 먼저 보내지 않고, commit할 때 반영
    - `expire_on_commit=False`
        - SQLAlchemy는 기본적으로 commit 후 객체 값을 만료시켜서 다시 조회함
        - 이 설정으로 JPA의 준영속 엔티티처럼 값을 유지하게 해서 불필요한 재조회를 줄임
        - 단, DB가 자동으로 만드는 값(자동 증가 id 등)은 `db.refresh(객체)`로 직접 다시 읽어야 함

**④ Base** → 모든 테이블 클래스의 부모 클래스 = DB 테이블과 연결된 클래스라는 것을 알려주는 것 (`@Entity`와 같은 역할)

- Base 클래스를 상속받으면 `Base.metadata`라는 테이블 목록에 자동으로 등록됨
- 서버가 시작될 때 `main.py`의 `Base.metadata.create_all(engine)`이 목록을 보고 테이블을 생성
    - 없는 테이블만 만든다. 이미 있는 테이블에 컬럼을 추가하지는 않음

**⑤ get_db()** → 요청마다 세션을 빌려주고 돌려받기

```python
def get_db():
    db = SessionLocal()    # 1. 새 세션 생성
    try:
        yield db           # 2. 세션을 빌려주고, 여기서 멈춰서 기다림
    finally:
        db.close()         # 3. 다 쓰면 반드시 닫기 (에러가 나도 실행됨)
```

- `yield` → 값을 돌려주고 함수를 잠시 멈춘다. 나중에 다시 돌아와서 다음 줄부터 이어서 실행
- 요청 1개 = 세션 1개 → 요청끼리 데이터가 섞이지 않음

```python
@router.get("/{product_id}")
def get_item(product_id: int, db: Session = Depends(get_db)):
    return product_service.find_by_id(db, product_id)
```

- `db: Session = Depends(get_db)` → 새로운 세션을 생성하여 `db`라는 변수에 세션을 담는다
    - `db`에 들어가는 건 데이터가 아니라 세션(작업대)
- 세션만 있으면 연결된 DB에서 상품을 가져올 수 있다 → 세션이 어느 DB에 연결해야 하는지 이미 알고 있기 때문
    - 세션(어느 DB) + 모델 클래스(어느 테이블) + id(몇 번)가 합쳐져서 SQL이 됨

```python
DATABASE_URL = "sqlite:///./coffee.db"            # ① DB 주소
engine = create_engine(DATABASE_URL)              # ② 그 주소로 연결하는 엔진
SessionLocal = sessionmaker(bind=engine)          # ③ 그 엔진을 쓰는 세션 공장
```

### 실제 로직 (services/product_service.py)

```python
def find_by_id(db: Session, product_id: int) -> Product:
#                                              ↑ "-> Product"는 반환 타입 (Java의 public Product)
    product = db.get(Product, product_id)
    #  ↑ PK로 조회. JPA의 em.find(Product.class, id) / repository.findById(id)

    if product is None:        # 없으면 (null 체크)
        raise NotFoundError(f"{product_id}번 상품을 찾을 수 없습니다.")
        #  ↑ throw new ... 와 같음. 이 에러는 main.py에서 404로 바뀜
    return product
```

- `@Service`로 Service 클래스를 선언하는 Spring Boot와 달리, Python은 별도의 어노테이션이 필요하지 않다
    - 클래스 없이 함수만 모아둔 파일(모듈)로 충분 → `product_service.find_by_id(...)`처럼 "파일이름.함수이름"으로 호출
- `raise 에러이름("메시지")` = `throw new 에러이름("메시지");`
- 기본 CRUD 함수는 세션이 제공한다 → 직접 구현할 필요 없음
    - `findById(id)` → `db.get(Product, id)`
    - `findAll()` → `db.scalars(select(Product))`
    - `save(p)` → `db.add(p)` + `db.commit()`
    - `delete(p)` → `db.delete(p)` + `db.commit()`
- 메서드 이름으로 쿼리를 자동 생성하는 기능(`findAllByCustomerEmail`)은 없음 → `select().where()`로 직접 작성
    - 예: `select(Order).where(Order.customer_email == email)`
- Repository 계층이 따로 없고, 세션이 Repository 역할을 한다
    - Spring: Controller → Service → Repository → DB
    - FastAPI: Router → Service → Session → DB

### 테이블 정의 (models.py)

```python
class Product(Base):                 # Base를 상속 = "이건 DB 테이블이야" (@Entity)
    __tablename__ = "product"        # 테이블 이름 (@Table)

    id: Mapped[int] = mapped_column("product_id", Integer, primary_key=True, autoincrement=True)
    #  ↑ 변수명 id, 실제 컬럼명 product_id, PK, 자동 증가
    #    = @Id @GeneratedValue(IDENTITY) @Column(name="product_id")

    name: Mapped[str] = mapped_column(String(50), nullable=False)
    #  ↑ @Column(nullable=false, length=50)

    image_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    #                  ↑ "str 또는 None" → null 허용

    def decrease_stock(self, quantity: int) -> None:
    #                  ↑ self = Java의 this. Python은 메서드 첫 번째 인자로 꼭 적음
        if self.stock < quantity:
            raise ValueError("재고가 부족합니다.")
        self.stock -= quantity
```

- Base 클래스를 상속받아야 DB 테이블 목록에 추가 가능
- 별도의 어노테이션 없이 `mapped_column(...)`에 옵션을 넘겨서 컬럼을 정의
- `Mapped`가 있어야 SQLAlchemy가 DB 컬럼임을 인식 가능 → `id: Mapped[int]` = `private Long id;`
    - Python은 `이름: 타입` 순서 (Java는 `타입 이름`)
    - `[int]`는 Java 제네릭의 `<Integer>`와 같음
    - 객체에서 쓰면 값(`product.id` → 3), 클래스에서 쓰면 컬럼(`Product.price <= 7000` → WHERE 조건)

## 2. Claude Tool Use

### Step 1. 요청 받기 (routers/chat.py)

```python
@router.post("/chat", response_model=ChatRes)
def chat(
    req: ChatReq,
    db: Session = Depends(get_db),
    client: anthropic.Anthropic = Depends(agent.get_claude_client),
):
    return agent.chat(db, client, req.message, req.history)
```

- `POST /chat` 요청을 받는다
- `req` → 요청 JSON (`{"message": "...", "history": [...]}`)
- `db` → 세션
- `client` → Claude API를 호출할 수 있는 객체
    - `Depends`로 받기 때문에 테스트할 때 가짜 Claude로 바꿔 끼우기 쉬움 (Spring의 `@MockBean`과 같은 아이디어)
- 실제 일은 `agent.py`의 `chat` 함수에게 맡긴다

### Step 2. Claude와 주고받기 (chat/agent.py)

**2-1. 대화 목록 만들기**

```python
def chat(db, client, message, history):
    messages = [{"role": m.role, "content": m.content} for m in history]
    messages.append({"role": "user", "content": message})
    tool_calls = []
```

- 1번째 줄 → 이전 대화(history)를 Claude API 형식(`{"role": ..., "content": ...}`)으로 바꿔서 messages 목록을 만든다
    - 우리 서버는 대화를 저장하지 않기 때문에, 이어지는 대화는 프론트엔드가 history로 보내줘야 함
- 2번째 줄 → 이번 질문을 messages 목록 마지막에 추가 = 지금까지의 대화 목록
- 3번째 줄 → Claude가 어떤 기능을 어떤 값으로 불렀는지 기록할 목록 (응답에 같이 담아서 보여줌)

**2-2. 반복 시작 + Claude에게 보내기**

```python
    for _ in range(MAX_TOOL_ROUNDS):
        response = client.beta.messages.create(
            model=MODEL,
            max_tokens=16000,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
            output_config={"effort": EFFORT},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
```

- 반복 1번 = Claude 호출 1번. 최종 답이 나오면 `return`으로 바로 반복문을 빠져나온다
    - 손님 메시지 1번에 Claude는 "기능 사용 횟수 + 1"번 호출됨
    - 예: "안녕하세요" → 1번 / "Ethiopia 원두 있어요?" → 2번 (검색) / "Ethiopia 원두 2개 주문해줘" → 3번 (검색 + 주문)
- `MAX_TOOL_ROUNDS`(8) → 무한 반복을 막는 안전장치
    - Claude API를 호출할 때마다 비용이 쌓이고, 반복이 계속되면 응답이 오지 않는다
- `_` → 반복 횟수 변수를 쓰지 않는다는 뜻
- `client.beta.messages.create(...)` → Claude API를 호출 = 인터넷을 통해 Claude에게 요청이 가고 답이 `response`에 담긴다
    - `model` = 사용할 Claude 모델
    - `max_tokens` = 답변 최대 길이
    - `system` = Claude의 역할과 규칙 (SYSTEM_PROMPT)
    - `tools` = Claude가 쓸 수 있는 기능 목록 (TOOLS)
    - `messages` = 지금까지의 대화 전체
    - `output_config` = 얼마나 깊게 생각할지
    - `betas`, `fallbacks` = Claude가 요청을 거절하면 다른 모델로 자동 재시도
- Claude는 이전 대화를 기억하지 못한다(stateless) → 매번 대화 전체를 다시 보낸다

**2-3. 응답 확인: 끝낼까, 기능을 실행할까?**

```python
        # Claude가 요청을 거절한 경우 → 거절 메시지를 돌려주고 끝
        if response.stop_reason == "refusal":
            return ChatRes(reply="죄송해요, 이 요청은 처리할 수 없어요.", tool_calls=tool_calls)

        # Claude가 잠깐 멈춘 경우 → 응답을 대화에 붙이고 반복문 처음으로 돌아가 다시 보냄
        if response.stop_reason == "pause_turn":
            messages.append({"role": "assistant", "content": response.content})
            continue

        # 응답 블록 중 type이 "tool_use"(기능 실행 요청)인 블록만 골라낸다
        tool_uses = [b for b in response.content if b.type == "tool_use"]

        # 실행 요청이 없다 = Claude가 최종 답변을 줬다 → text 블록의 글만 이어 붙여서 반환
        if response.stop_reason != "tool_use" or not tool_uses:
            reply = "".join(b.text for b in response.content if b.type == "text").strip()
            return ChatRes(reply=reply or "(응답이 비어 있습니다)", tool_calls=tool_calls)
```

- `response.stop_reason` → Claude가 왜 멈췄는지 (Claude가 정해서 알려줌)
    - `"tool_use"` → 기능 실행해줘 (최종 답 아님)
    - `"end_turn"` → 할 말 다 했어 (최종 답)
    - `"refusal"` → 이건 처리 못 해
    - `"pause_turn"` → 잠깐 멈췄어, 이어서 보내줘
- `response.content` → Claude가 보낸 블록(조각)들의 목록
    - `type: "text"` → Claude가 한 말 (`text`)
    - `type: "tool_use"` → 기능 실행 요청서 (`id`, `name`, `input`)

```python
response.content = [
    {"type": "text", "text": "찾아볼게요."},
    {"type": "tool_use", "id": "t1", "name": "search_products",
     "input": {"keyword": "Ethiopia", "max_price": None, "in_stock_only": True}},
]
```

- `"".join(...)` → 글자들을 이어 붙임 (Java의 `String.join`), `.strip()` → 앞뒤 공백 제거 (Java의 `trim()`)

**2-4. 요청받은 기능 실행하기**

```python
        # Claude의 응답(실행 요청 포함)을 messages 목록에 추가
        messages.append({"role": "assistant", "content": response.content})

        tool_results = []

        # 기능 실행 요청을 하나씩 꺼낸다
        for block in tool_uses:
            # 실제 기능 실행 → (결과 JSON 문자열, 에러 여부) 두 값을 돌려받음
            output, is_error = run_tool(db, block.name, block.input)

            # 어떤 기능을 어떤 값으로 불렀는지 기록 (응답에 같이 보여주는 용도)
            tool_calls.append(ToolCallLog(name=block.name, input=block.input,
                                          output=output, is_error=is_error))

            # Claude에게 돌려보낼 실행 결과
            tool_results.append({
                "type": "tool_result",       # 이건 실행 결과야
                "tool_use_id": block.id,     # 어떤 실행 요청(t1)에 대한 결과인지 짝 맞추기
                "content": output,           # 실행 결과
                "is_error": is_error,        # 에러였는지
            })
```

- Claude의 응답을 대화에 넣는 이유 → Claude는 기억이 없어서, "내가 t1번으로 실행을 요청했다"는 기록이 없으면 결과가 무엇에 대한 것인지 모름
- 기능 실행 결과 예시

```python
output   = '{"count": 1, "products": [{"id": 4, "name": "Ethiopia Sidamo", "price": 8000, ...}]}'
is_error = False
```

**2-5. 실행 결과를 대화에 추가하고 다시 처음으로**

```python
        # ⚠️ for block 반복문 "바깥"에 있어야 함 → 결과를 모두 모은 다음 한 번만 추가
        messages.append({"role": "user", "content": tool_results})
        # → 반복문 처음(2-2)으로 돌아가 Claude에게 다시 보냄
        # → Claude가 결과를 보고 다음 행동을 정함 (기능 추가 요청 or 최종 답변)

    # 8번을 다 돌아도 끝나지 않으면 여기로 옴 (안전장치)
    return ChatRes(reply="요청을 처리하는 데 너무 많은 단계가 필요했어요...", tool_calls=tool_calls)
```

- ⭐ Python은 중괄호 `{}` 대신 들여쓰기로 블록을 구분한다 → 들여쓰기 위치가 바뀌면 동작이 바뀜
- `role`은 "누가 보냈는지"가 기준
    - `assistant` → Claude가 보낸 것 (답변, 실행 요청)
    - `user` → Claude 바깥에서 보낸 것 (손님 질문, 우리 서버의 실행 결과)
    - Claude API에는 이 두 역할만 있음. 실행 결과는 우리 서버가 보내는 바깥 정보라서 `user`
    - 손님 말과 실행 결과는 `type: "tool_result"`와 `tool_use_id`로 구분됨

### Step 3. 기능 목록 + 실행 (chat/tools.py)

**3-1. 기능 목록 (실행되는 코드가 아닌 단순 데이터 목록)**

```python
TOOLS = [
    {
        # 기능 이름 (Claude가 실행 요청할 때 이 이름을 씀 → block.name)
        "name": "search_products",
        # 기능을 언제 사용하는지에 대한 설명 (Claude가 읽고 판단)
        "description": "카페에서 판매하는 원두 상품을 검색합니다. ...",
        # 양식을 정확히 지키게 설정
        "strict": True,
        # 기능에 넘길 값의 양식 (Claude가 이 양식대로 값을 채움 → block.input)
        "input_schema": {
            "type": "object",
            "properties": {
                "keyword":       {"type": ["string", "null"]},
                "max_price":     {"type": ["integer", "null"]},
                "in_stock_only": {"type": "boolean"},
            },
            "required": ["keyword", "max_price", "in_stock_only"],
            "additionalProperties": False,
        },
    },
    { "name": "create_order", ... },
    { "name": "get_orders", ... },
]
```

- `client.beta.messages.create(tools=TOOLS)`로 Claude에게 그대로 보내짐
- `input_schema`는 1부의 Pydantic 요청 양식과 같은 역할 → 차이는 사람 대신 Claude가 양식을 채운다는 것
- `description`을 어떻게 쓰느냐에 따라 Claude의 행동이 달라짐
    - 예: 상품 이름이 영어라서 한글 "에티오피아"로 검색하면 0개 → description에 "keyword는 영어로"라고 적어주면 개선 가능

**3-2. 실제 실행 함수**

```python
def _search_products(db, keyword, max_price, in_stock_only):
    # Service의 search 함수를 그대로 재사용해서 상품을 찾는다 → Product 객체(Entity) 목록
    products = product_service.search(db, keyword=keyword, max_price=max_price, in_stock_only=in_stock_only)
    # count = 검색에 걸린 상품의 개수 (Java의 size())
    # products = 하나씩 꺼내서 Entity → DTO(model_validate) → dict(model_dump)로 변환
    # Claude에게는 글자(JSON 문자열)로만 보낼 수 있기 때문에 dict 변환 필수 (Entity는 JSON 변환 불가)
    return {"count": len(products),
            "products": [ProductDto.model_validate(p).model_dump() for p in products]}
```

- `keyword=keyword` → 왼쪽은 search 함수의 파라미터 이름, 오른쪽은 지금 함수의 변수 값 (키워드 인자)
- `[... for p in products]` → 리스트 컴프리헨션. 목록을 하나씩 꺼내서 변환한 새 목록을 만든다 (Java의 stream map)
- 함수 이름 앞의 `_` → 이 파일 안에서만 쓰는 함수라는 Python 관례 (Java의 `private`와 비슷)

**3-3. 이름 → 함수 연결표**

```python
_HANDLERS = {
    "search_products": _search_products,
    "create_order":    _create_order,
    "get_orders":      _get_orders,
}
```

- ⭐ `_search_products`(괄호 없음) → 함수 실행 결과를 저장하는 게 아니라 **함수 자체**를 저장
    - `_search_products(...)` (괄호 O) → 함수를 실행
    - `_search_products` (괄호 X) → 함수 그 자체
- ⭐ Python에서는 함수 이름을 그대로 값처럼 변수나 dict에 넣을 수 있다
    - Java도 메서드 참조(`this::searchProducts`)와 `Map<String, Function>`으로 비슷하게 가능하지만, Python이 더 간단
- 연결표를 만드는 이유: Claude는 기능 이름을 **문자열**로 보내기 때문에, 우리 코드(`run_tool`)가 그 문자열로 함수를 찾을 연결표가 필요
    - 연결표가 없으면 if-elif 문을 계속 써야 함
    - 기능이 늘어나도 `_HANDLERS`에 한 줄만 추가하면 됨

**3-4. 연결표에서 찾아서 실행**

```python
def run_tool(db, name, tool_input):
    # 기능 이름(문자열)으로 실행할 함수를 꺼낸다
    handler = _HANDLERS.get(name)

    # 목록에 없는 이름이면 에러 결과를 반환
    if handler is None:
        return json.dumps({"error": f"알 수 없는 tool: {name}"}, ensure_ascii=False), True

    try:
        # **tool_input = dict를 풀어서 '이름=값'으로 넣는다 → 함수 실행
        result = handler(db, **tool_input)
        # dict를 JSON 문자열로 바꿔서 (결과, 에러 아님) 반환
        return json.dumps(result, ensure_ascii=False), False
    except (NotFoundError, BusinessError) as e:
        # 에러를 raise로 던지지 않고 (에러 내용, 에러임)으로 돌려준다
        return json.dumps({"error": str(e)}, ensure_ascii=False), True
```

- 반환값은 두 개 → **(결과 JSON 문자열, 에러 여부)**
- `handler = _HANDLERS.get(name)` → 연결표에서 이름으로 실행할 함수를 꺼낸다

```python
handler(db, **{"keyword": "Ethiopia", "max_price": None, "in_stock_only": True})
# ↓ 이렇게 바뀌어서 실행됨
_search_products(db, keyword="Ethiopia", max_price=None, in_stock_only=True)
```

- `json.dumps(...)` → dict를 JSON 문자열로 변환 (Java의 `objectMapper.writeValueAsString`)
- `ensure_ascii=False` → 한글이 `\uXXXX`처럼 깨지지 않게
- ⭐ 에러를 던지지 않고 결과로 돌려주는 이유
    - `raise`로 던지면 → 서버가 에러 응답을 보내고 대화가 끝남. Claude는 무슨 일이 있었는지 모름
    - 결과로 돌려주면 → Claude가 에러 내용을 보고 손님에게 설명해줌 (예: "재고가 3개 남았어요. 3개로 주문할까요?")

### 전체 흐름

```text
POST /chat {"message": "Ethiopia 원두 있어요?"}
│
① routers/chat.py: agent.chat(db, client, "Ethiopia 원두 있어요?", [])
│
② chat/agent.py
│  [2-1] messages = [user: "Ethiopia 원두 있어요?"]
│
│  ── 반복 1 ──
│  [2-2] Claude에게 전송
│  [2-3] stop_reason = "tool_use" → 통과
│  [2-4] messages에 Claude 응답(assistant) 추가
│         run_tool(db, "search_products", {"keyword": "Ethiopia", ...})
│            ③ chat/tools.py: _HANDLERS → _search_products → product_service.search
│            → ('{"count": 1, "products": [Ethiopia Sidamo ...]}', False)
│  [2-5] messages에 실행 결과(user, tool_result) 추가
│
│  ── 반복 2 ──
│  [2-2] Claude에게 전송 (대화 전체)
│  [2-3] stop_reason = "end_turn" → return
│
응답: {"reply": "네! Ethiopia Sidamo가 8,000원에 있어요.",
       "tool_calls": [{"name": "search_products", ...}]}
```

### Tool Use와 AI Agent

- Tool Use → Claude가 우리 기능을 고르고 실행을 **요청**할 수 있게 해주는 기술. 실제 실행은 우리 서버가 함
- AI Agent → Tool Use를 **반복**하면서, 결과를 보고 다음 행동을 스스로 정해 목표를 끝까지 해내는 구조
    - 검색 → 주문 순서를 코드로 정하지 않았는데, Claude가 "주문하려면 id가 필요하니 먼저 검색하자"라고 스스로 판단
