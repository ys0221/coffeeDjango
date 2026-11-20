# 데브코스 1차 프로젝트를 FastAPI로 변환하고 Claude API 호출해보기

## 0. 학습 배경

1. Spring Boot로 백엔드 개발과 서비스 구조를 익힘
2. AI 활용이 늘어나면서, AI 기능을 붙이기 좋은 기술 환경에 관심이 생김
3. AI 관련 SDK와 라이브러리가 Python에 가장 풍부하다는 걸 알게 됨
4. Python 웹 프레임워크(Django, Flask, FastAPI)를 비교 → API 중심 서비스에는 FastAPI가 적합하다고 판단
5. 기존 Spring 프로젝트를 FastAPI로 옮기고, Claude API의 Tool Use로 AI Agent를 붙이며 학습

(Python과 FastAPI를 고른 이유는 "4. 면접용 개념 정리 → A"에 정리)

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

### 주문 생성 POST /orders (트랜잭션)

요청이 들어와서 응답이 나갈 때까지 5단계를 거친다.

```text
POST /orders (JSON)
 ① schemas.py           요청 JSON 검사
 ② routers/orders.py    서비스에 넘기기 좋게 변환
 ③ order_service.py     재고 차감 + 주문 저장 (트랜잭션) ⭐
 ④ routers/orders.py    응답 만들기
 ⑤ main.py              에러가 났다면 400/404로 바꾸기
```

**① 요청 JSON 검사 (schemas.py)**

```python
class OrderItemReq(BaseModel):        # 주문 항목 1개의 양식 (BaseModel 상속 = DTO)
    product_id: int                   # 상품 번호 (필수, 숫자)
    quantity: int = Field(ge=1)       # 수량 (필수, 1 이상) = @Min(1)

class OrderCreateReq(BaseModel):      # 주문 요청 전체의 양식
    customer_email: str = Field(min_length=3)        # 이메일 (3글자 이상)
    items: list[OrderItemReq] = Field(min_length=1)  # 주문 항목 목록 (최소 1개)
```

```json
{
  "customer_email": "a@test.com",
  "items": [
    {"product_id": 1, "quantity": 2},
    {"product_id": 4, "quantity": 1}
  ]
}
```

- `list[OrderItemReq]` → OrderItemReq 양식의 목록 = Java의 `List<OrderItemReq>`
- 양식이 틀리면 서비스까지 가지 않고 FastAPI가 바로 422 에러를 돌려준다 (`@Valid` 실패와 같음)
    - `"quantity": 0`, `"items": []`, `"product_id": "abc"`, 필수값 누락 → 422

**② 서비스에 넘기기 (routers/orders.py)**

```python
@router.post("", response_model=RsData[list[OrderDto]], status_code=201, summary="주문")
def create_order(req: OrderCreateReq, db: Session = Depends(get_db)):
    orders = order_service.create_order(
        db,
        req.customer_email,
        [(i.product_id, i.quantity) for i in req.items],   # → [(1, 2), (4, 1)]
    )
```

- `[(i.product_id, i.quantity) for i in req.items]` → 리스트 컴프리헨션으로 (상품번호, 수량) 묶음의 목록을 만든다
- `(1, 2)`처럼 괄호로 묶은 값 = 튜플 (값 여러 개를 하나로 묶은 것)

**③ ⭐ 재고 차감 + 주문 저장 (services/order_service.py)**

```python
def create_order(db: Session, customer_email: str, items: list[tuple[int, int]]) -> list[Order]:
    if not items:                                     # (A) 목록이 비었으면 바로 에러 (= isEmpty())
        raise BusinessError("주문 항목이 비어 있습니다.")

    now = datetime.now()                              # (B) 주문 시각 (모든 항목에 같은 시각)
    orders: list[Order] = []

    try:
        for product_id, quantity in items:            # (C) 튜플을 꺼내서 두 변수에 나눠 담기
            if quantity < 1:
                raise BusinessError("수량은 1 이상이어야 합니다.")

            product = db.get(Product, product_id)     # (D) 상품 찾기
            if product is None:
                raise NotFoundError(f"{product_id}번 상품을 찾을 수 없습니다.")

            try:                                      # (E) 재고 줄이기
                product.decrease_stock(quantity)
            except ValueError as e:
                raise BusinessError(f"{product.name}: {e} (남은 재고 {product.stock}개)") from e

            order = Order(                            # (F) 주문 객체 만들기 (빌더 불필요)
                customer_email=customer_email,
                product_id=product_id,
                order_date=now,
                order_state=False,
                quantity=quantity,
            )
            db.add(order)                             # (G) 세션에 "저장 예정"으로 올리기
            orders.append(order)

        db.commit()                                   # (H) 전부 성공 → DB에 한 번에 반영
    except Exception:
        db.rollback()                                 # (I) 하나라도 실패 → 전부 취소
        raise                                         #     잡은 에러를 그대로 다시 던짐

    for o in orders:                                  # (J) DB가 만든 값(order_id) 다시 읽기
        db.refresh(o)
    return orders
```

- (A) 라우터에서 이미 검사했지만, 이 함수는 Claude Tool에서도 호출하기 때문에 한 번 더 막는다
- (C) `for product_id, quantity in items` → 반복할 때마다 튜플 하나를 꺼내서 두 변수에 나눠 담는다
    - 1번째 반복: `product_id = 1, quantity = 2` / 2번째 반복: `product_id = 4, quantity = 1`
- (E) 재고 부족 `ValueError`를 잡아서 친절한 메시지의 `BusinessError`로 바꿔 던진다
    - `raise ... from e` → 원래 에러(e)를 원인으로 남겨둠 = Java의 `throw new BusinessException(msg, e);`
    - `BusinessError`로 바꿔야 ⑤에서 400 응답으로 처리된다
- (G) `db.add()`는 아직 DB에 들어간 게 아님. 세션(장바구니)에 올려두기만 한 것. 재고 감소도 아직 객체 안에서만 바뀐 상태
- (H) 반복문이 전부 끝나야 commit까지 온다 → 모아둔 UPDATE, INSERT가 한 번에 DB로
- (I) `try` 안 어디서든 에러가 나면 여기로 온다
    - `db.rollback()` → 앞에서 줄인 재고, add한 주문 전부 없던 일로
    - `raise` (뒤에 아무것도 없음) → 잡은 에러를 그대로 다시 위로 던짐 = Java의 `throw e;`
    - 여기서 에러를 삼키면 라우터는 성공한 줄 안다
- (J) `expire_on_commit=False`라서 commit 후 자동으로 다시 읽지 않음 → 자동 증가 `order_id`를 `db.refresh()`로 직접 읽어온다
- 트랜잭션은 `try`에서 시작되는 게 아니라, 세션이 처음 DB를 쓸 때(`db.get`) 자동으로 시작된다. `try`는 "여기서 에러 나면 롤백"할 범위를 정하는 것
- ⭐ Spring의 `@Transactional`이 자동으로 해주던 commit/rollback을 직접 쓴 것

**시나리오** (처음 재고: 1번 상품 100개, 4번 상품 2개)

```text
✅ 성공: [(1, 2), (4, 1)]
  1번 처리 → 1번 재고 98, 주문1 add          (DB 변화 없음)
  4번 처리 → 4번 재고 1,  주문2 add          (DB 변화 없음)
  commit  → DB에 재고 98, 1 + 주문 2건 저장

❌ 실패: [(1, 2), (4, 5)]   ← 4번 재고는 2개뿐
  1번 처리 → 1번 재고 98, 주문1 add          (DB 변화 없음)
  4번 처리 → 💥 재고 부족 BusinessError
  rollback → 1번 재고도 100으로 복구, DB 변화 없음
```

- 1번 상품의 재고 감소까지 함께 취소되는 것이 트랜잭션의 핵심
- `tests/test_crud.py`의 `test_order_out_of_stock_rolls_back` 테스트로 확인

**Spring 버전과 차이 (개선한 점)**

- Spring 버전은 컨트롤러에서 `for (OrderDto dto : reqBody) orderService.createOrder(dto);` → 상품마다 트랜잭션을 따로 열었음
    - 3개 중 3번째가 재고 부족이면 1, 2번째 주문은 이미 저장됨 (일부만 주문되는 문제)
    - 또 주문을 먼저 저장한 뒤 재고를 확인했음
- FastAPI 버전은 주문 전체를 하나의 트랜잭션으로 처리 → 하나라도 실패하면 전부 취소

**④ 응답 만들기 (routers/orders.py)**

```python
    msg = order_service.delivery_message(orders[0].order_date, "주문")
    return RsData(resultCode="201-1", msg=msg,
                  data=[OrderDto.model_validate(o) for o in orders])
```

- `delivery_message` → 오후 2시 기준 배송 안내 문구 (Spring 컨트롤러에 있던 로직 그대로)
    - 14시 이후: "당일 오후 2시 이후의 주문 건은 다음 날 배송이 시작됩니다."
    - 14시 이전: "주문이 완료되었습니다. 배송은 금일 시작됩니다."
- 주문 Entity 목록 → DTO 목록으로 변환해서 `RsData`에 담아 응답

**⑤ 에러를 HTTP 응답으로 (main.py)**

```python
@app.exception_handler(BusinessError)            # BusinessError가 오면 (@ExceptionHandler)
async def handle_business(_: Request, e: BusinessError):
    return JSONResponse(
        status_code=400,
        content={"resultCode": "400-1", "msg": str(e), "data": None},
    )
```

- ③에서 `raise`로 다시 던진 에러가 라우터를 통과해서 여기로 온다 (`@RestControllerAdvice`와 같음)
- `str(e)` → 에러 메시지 꺼내기 = Java의 `e.getMessage()`
- `_` → 사용하지 않는 파라미터라는 Python 관례
- `NotFoundError`(없는 상품) → 404 / `BusinessError`(재고 부족) → 400

```text
POST /orders {"customer_email": "a@test.com", "items": [{1, 2}, {4, 5}]}
 ① 양식 검사 통과
 ② [(1, 2), (4, 5)] 로 변환해서 서비스 호출
 ③ 1번 재고 100→98, 주문1 add → 4번 재고 부족 💥 → rollback (1번 재고 100으로 복구) → raise
 ⑤ BusinessError 잡음 → 400 응답
 응답: {"resultCode": "400-1", "msg": "Ethiopia Sidamo: 재고가 부족합니다. (남은 재고 2개)"}
```

**💡 한계와 개선 방법 (면접 대비)**

- 동시 주문 문제: 두 사람이 동시에 마지막 재고 1개를 주문하면 둘 다 "재고 1개"를 읽고 둘 다 성공할 수 있음 (Spring 버전도 동일)
- 해결 방법
    - 비관적 락: 조회할 때 잠금 (`SELECT ... FOR UPDATE`, SQLAlchemy의 `with_for_update()`)
    - 낙관적 락: 버전 컬럼으로 충돌 감지 (JPA의 `@Version`)

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


## 3. Claude API 실행 시나리오

실제 Claude API 키로 서버를 실행하고, Swagger(`/docs`)에서 `POST /chat`을 호출한 결과. 응답 JSON은 핵심 부분만 줄여서 적음.

### 시나리오 1. 7000원 이하 원두 찾기

```json
"tool_calls": [
  {"name": "search_products",
   "input": {"keyword": null, "max_price": 7000, "in_stock_only": true},
   "output": "{\"count\": 3, \"products\": [Columbia Nariño 5000, Brazil 6000, Columbia Quindío 7000]}"}
]
"reply": "7,000원 이하이면서 지금 바로 주문할 수 있는 원두는 3가지예요. ..."
```

- 7,000원 → `max_price = 7000`으로 바꿔서 `search_products` 호출
- 서버 → DB를 검색하여 3가지를 찾음
- Claude → 결과를 보고 정리하여 답변
- 손님이 말하지 않은 `in_stock_only: true`도 "추천이니까 살 수 있는 것만"이라고 Claude가 스스로 판단해서 넣음

⭐ **Tool Use의 기본 동작:** `input_schema`(keyword, max_price, in_stock_only)에 적어둔 양식을 Claude가 읽고 사람의 말을 그 양식에 맞게 채움 = 자연어(7000원 이하)를 Tool의 입력값(`max_price`)으로 바꿈

### 시나리오 2. 가장 인기 있는 원두 찾기

```json
"tool_calls": [
  {"name": "search_products",
   "input": {"keyword": null, "max_price": null, "in_stock_only": true},
   "output": "{\"count\": 4, \"products\": [id, name, price, stock만 있음]}"}
]
"reply": "죄송하지만 저희 시스템에는 판매량이나 인기 순위 정보가 없어서 \"가장 인기 있는 원두\"는 알려드릴 수 없어요. 대신 ..."
```

- `output`에 인기, 판매량 정보가 없다 → reply에서 "판매량이나 인기 순위 정보가 없어서 알려드릴 수 없어요"

⭐ `SYSTEM_PROMPT`에 "추측하지 말고 Tool로 확인하라"는 규칙을 넣었기 때문에 Claude가 지어내지 않고 솔직하게 답변 (환각 방지)

### 시나리오 3. 에티오피아 원두 주문 요청

```json
"tool_calls": [
  {"name": "search_products",
   "input": {"keyword": "에티오피아", "max_price": null, "in_stock_only": false},
   "output": "{\"count\": 0, \"products\": []}"},
  {"name": "search_products",
   "input": {"keyword": "Ethiopia", "max_price": null, "in_stock_only": false},
   "output": "{\"count\": 1, \"products\": [{\"id\": 4, \"name\": \"Ethiopia Sidamo\", \"price\": 8000, \"stock\": 100}]}"}
]
"reply": "에티오피아 원두는 지금 1종 있어요. Ethiopia Sidamo: 8,000원 ..."
```

DB에는 상품 이름이 모두 영어로 되어 있다.

- 한글로 검색하면 서버가 상품을 찾지 못한다 (`WHERE name LIKE '%에티오피아%'`)
- 서버가 count: 0 결과를 Claude에게 돌려주고, **Claude가 그걸 보고 스스로 번역해서** 다시 검색한다
    - 코드에는 번역이나 재검색 로직이 존재하지 않는다 = 반복문이 결과를 다시 Claude에게 보내주기 때문에 가능
- 하지만 Claude 호출 횟수가 1번 늘어서(2번 → 3번) 비용과 응답 시간이 는다 → Tool 설명에 "상품명은 영어"라고 적어주는 것이 좋음

⭐ **결과를 보고 다음 행동을 스스로 바꾼 AI Agent의 대표 장면**

### 시나리오 4. 디테일한 요청 (선물 추천)

```json
{"message": "친구한테 선물하려고 하는 어떤 원두 추천해? 그 친구는 산미가 있는 커피를 좋아해"}
```

```json
"tool_calls": [
  {"name": "search_products",
   "input": {"keyword": null, "max_price": null, "in_stock_only": true},
   "output": "{\"count\": 4, ...}"}
]
"reply": "1. Ethiopia Sidamo (8,000원) 에티오피아 원두는 보통 꽃향과 상큼한 과일 산미로 ...
          2. Columbia Quindío (7,000원) 발효 시간을 늘려 가공한 원두라서 ...
          맛 설명은 원산지와 가공 방식의 일반적인 특징을 바탕으로 한 거예요.
          상품 정보에 맛 노트가 따로 없어서 실제 맛은 조금 다를 수 있어요."
```

- `output`에는 맛 정보가 존재하지 않는다 → Claude가 원래 알고 있는 일반 지식으로 답변
- Tool로 가져온 가게 데이터(가격, 재고)와 LLM의 일반 지식(원산지 특징)을 결합해서 추천
- 시나리오 2(인기 순위는 가게만의 정보라 "모른다")와 달리, 일반 지식으로 답하되 **출처의 한계를 밝힘**

### 시나리오 5. 주문 요청

```json
{"message": "Ethiopia Sidamo 2개 주문할게요. 이메일은 test@test.com 이에요"}
```

```json
"tool_calls": [
  {"name": "search_products",
   "input": {"keyword": "Sidamo", "max_price": null, "in_stock_only": false},
   "output": "{\"count\": 1, \"products\": [{\"id\": 4, \"name\": \"Ethiopia Sidamo\", \"price\": 8000, \"stock\": 100}]}"}
]
"reply": "주문하시기 전에 아래 내용을 확인해 주세요. 이메일: test@test.com / 상품: Ethiopia Sidamo × 2개 / 총액: 16,000원 ... 이대로 주문할까요?"
```

- 주문 정보가 다 있어도 바로 주문하지 않고 총액을 보여주며 확인을 받았다
- `tool_calls`에 `create_order`가 없다 = 실제로 주문하지 않았다는 증거
- `SYSTEM_PROMPT`에 "확인 없이 주문하지 마라"는 규칙이 있었기 때문 (Human-in-the-loop)

### 시나리오 6. 실제 주문 ⭐

**요청**

```json
{
  "message": "네, 주문해주세요",
  "history": [
    {"role": "user", "content": "Ethiopia Sidamo 2개 주문할게요. 이메일은 test@test.com 이에요"},
    {"role": "assistant", "content": "주문하시기 전에 아래 내용을 확인해 주세요. ... 이대로 주문할까요?"}
  ]
}
```

**응답**

```json
"tool_calls": [
  {"name": "search_products",
   "input": {"keyword": "Ethiopia Sidamo", ...},
   "output": "{\"count\": 1, \"products\": [{\"id\": 4, ... \"stock\": 100}]}"},
  {"name": "create_order",
   "input": {"customer_email": "test@test.com", "items": [{"product_id": 4, "quantity": 2}]},
   "output": "{\"message\": \"당일 오후 2시 이후의 주문 건은 다음 날 배송이 시작됩니다.\", \"total_price\": 16000,
              \"orders\": [{\"order_id\": 1, \"order_date\": \"2026-11-18T21:46:46\", \"quantity\": 2,
              \"product\": {\"id\": 4, \"stock\": 98}}]}"}
]
"reply": "주문이 완료됐어요. 주문번호: 1 / 총액: 16,000원 / 오후 2시 이후(21:46)에 주문하셔서 내일 배송이 시작돼요.
          참고로 지난번 답변에서는 가격과 재고를 확인하지 않고 말씀드렸어요. ..."
```

**재고 확인 (`GET /products/4`)** → 실제로 2개가 줄어 있음

```json
{"id": 4, "name": "Ethiopia Sidamo", "price": 8000, "stock": 98}
```

- 서버는 대화를 저장하지 않기 때문에, "네, 주문해주세요"만 보내면 Claude는 무엇을 주문하라는 건지 알 수 없다 = 이전 대화를 `history`에 담아 보낸 이유
- 주문을 위해 상품 id를 검색 → 2개 주문 = 대화 앞부분의 정보(이메일, 수량) + 방금 받은 검색 결과(id=4)를 조합하여 주문 값을 생성
- 손님의 말 한마디 → Claude의 판단 → 서비스 함수 실행 → **실제 DB 변경**까지 확인

🚨 **문제 발견 (구조의 한계)**

1. `history`에 텍스트만 넣어서 Claude가 이전에 검색한 기록을 볼 수 없었다 → "가격과 재고를 확인하지 않고 말했다"고 사실과 다르게 판단
2. 주문할 때 상품 id가 필요한데, 시나리오 5의 답변(텍스트)에는 상품 id가 없어서 다시 검색할 수밖에 없었다

이 때문에 검색을 한 번 더 하게 되고(비용, 시간 증가), 잘못된 안내로 서비스에 대한 신뢰가 떨어질 수 있다.

```text
시나리오 5에서 실제로 오간 대화          history로 넘어간 것
user:      "2개 주문할게요..."          user:      "2개 주문할게요..."
assistant: [검색 요청: Sidamo]          (빠짐)
user:      [검색 결과: id=4, 8000원]     (빠짐)
assistant: "확인해 주세요..."           assistant: "확인해 주세요..."
```

✍️ **개선 방안**

현재 구조는 같은 대화에서 지금까지 오간 말을 전부, 순서대로 `history`에 넣어야 한다. 이때 `history`는 텍스트만 받는다. 따라서 맥락을 빠짐없이 전달하려면 **Tool 기록(Claude가 한 말의 근거 자료)까지 포함한 대화 전체**를 저장하거나 주고받는 구조가 필요하다.

1. 서버가 대화 전체(`messages`)를 저장 → 프론트엔드는 `history` 대신 대화 ID만 보낸다
    - `reply`만 저장하면 Tool 기록은 저장되지 않는다
    - 마지막 답변도 `messages`에 붙여서 저장해야 한다
    - 함께 고민할 것: 대화가 길어질 때의 비용, 저장 기간(TTL), 다른 사람의 대화 ID로 접근하는 문제(인증)
2. 응답에 Tool 기록까지 포함한 대화 전체를 담아 돌려주고, 다음 요청 때 그대로 다시 보내기

참고: 주문처럼 되돌리기 어려운 작업 직전에 최신 재고를 다시 확인하는 것 자체는 좋은 습관일 수 있다. 문제는 재검색이 아니라 "확인하지 않았다"는 잘못된 안내.

⭐ **LLM에게 판단에 필요한 맥락을 빠짐없이 전달해야 한다**

### 시나리오 7. 재고보다 많이 주문하기

```json
{"message": "Brazil Serra Do Caparaó 500개 주문할게요. 이메일은 test@test.com 이에요"}
```

```json
"tool_calls": [
  {"name": "search_products",
   "input": {"keyword": "Brazil", ...},
   "output": "{\"count\": 1, \"products\": [{\"id\": 2, \"name\": \"Brazil Serra Do Caparaó\", \"price\": 6000, \"stock\": 100}]}"}
]
"reply": "재고가 100개뿐이에요. 500개는 한 번에 주문할 수 없어요.
          1. 재고 100개만 주문 (총액 600,000원)  2. 부족한 400개는 다른 원두로 채우기 ..."
```

- 재고 처리 장치 두 겹
    - **1겹 (이번에 동작함):** Claude가 검색 결과(재고 100개)를 보고 미리 판단 → 주문을 시도하지 않고 대안을 제시
    - **2겹 (이번엔 실행 안 됨):** 만약 주문을 시도했다면 `order_service`가 재고 부족 에러 → 롤백 → Claude에게 `is_error: true`로 전달. 테스트 코드(`test_chat_tool_error_is_returned_to_claude`)로 검증
- 두 겹이 필요한 이유: AI의 판단에만 의존하지 않고 코드 레벨의 검증을 함께 둔 것

### 시나리오별 Agent다운 장면

| 시나리오 | 확인한 것 | 핵심 키워드 |
|---|---|---|
| 1 | 자연어를 Tool 입력값으로 변환 | Tool Use 기본 |
| 2 | 없는 정보를 지어내지 않음 | 환각 방지 |
| 3 | 실패한 검색을 스스로 복구 | 결과를 보고 행동을 바꿈 |
| 4 | 가게 데이터 + 일반 지식 결합, 한계를 밝힘 | RAG 필요성 |
| 5 | 행동할 수 있어도 멈추고 확인 요청 | Human-in-the-loop |
| 6 | 검색 → 주문 → 실제 DB 변경, history 한계 발견 | 핵심 증거 + 맥락 관리 |
| 7 | 재고를 미리 확인해서 계획을 바꿈 | 이중 안전장치 |

### API 실행하면서 느낀 점

1. **SYSTEM_PROMPT 규칙의 중요성:** 데이터의 정확성과 신뢰를 위해서는 올바른 규칙을 세우는 것이 중요하다는 걸 느꼈다. (시나리오 2: 판매량을 지어내지 않음 / 시나리오 5: 주문 전 확인)
2. **검색 이름 불일치 대비:** 당장은 Tool 설명에 "상품명은 영어"라고 적어 개선할 수 있고, 근본적으로는 한글 이름 컬럼을 추가해 둘 다 검색되게 하는 방식을 고려해봐야겠다. (시나리오 3)
3. **가게 데이터와 일반 지식의 구분:** 맛 정보가 없어 답을 못 할 거라 예상했는데, Claude가 Tool로 가져온 가게 데이터와 자신이 가진 일반 지식을 결합해서 산미 있는 원두를 추천했다. 모든 정보를 DB에 일일이 저장하지 않아도 두 정보를 함께 활용할 수 있다는 점이 AI Agent의 큰 장점으로 와닿았다. 하지만 틀린 정보를 말하는 것을 막으려면 지금처럼 가격과 재고같이 틀리면 안 되는 정보는 반드시 Tool로 조회하게 하고, 일반 지식으로 답할 때는 한계를 밝히는 것을 규칙으로 명시해야 할 것 같다. (지금은 Claude가 스스로 판단하여 한계를 밝혔던 것) (시나리오 4)
4. **맥락은 빠짐없이:** LLM은 이전 대화를 기억하지 못하고 전달받은 정보만으로 판단한다. 따라서 판단에 필요한 맥락과 Tool 기록까지 빠짐없이 전달하지 않으면 같은 검색을 반복해 비용과 시간이 늘고, 사실과 다른 안내로 신뢰가 떨어질 수 있다. (시나리오 6)
5. **AI에만 의존하지 않는 설계:** AI 판단에만 의존하지 않도록 안전장치를 겹겹이 두는 설계가 필요하다. 규칙이 명확한 건 코드로 한 번 더 검증하고(시나리오 7: 재고 검증과 롤백), 되돌리기 어려운 작업은 사람의 확인을 받아야 한다(시나리오 5: 주문 전 확인).

## 4. 면접용 개념 정리

코드 문법보다 **"이 단어를 물어보면 한두 문장으로 답할 수 있어야 하는 것"** 위주.

| 순위 | 묶음 | 이유 |
|---|---|---|
| 1 | C. LLM / AI Agent 개념 | AI Agent 회사라 가장 많이 물어봄 |
| 2 | A. 왜 Python / FastAPI인가 | 지원 동기와 바로 연결 |
| 3 | D. 안전한 Agent 설계 | 실험에서 직접 겪은 내용이라 강점 |
| 4 | B. 백엔드 기본 | Spring으로 아는 내용 복습 |
| 5 | E. 자소서 연결 개념 | 자소서에 쓴 단어는 반드시 물어봄 |

### A. 왜 Python / FastAPI인가

**Python이 AI 개발에 많이 쓰이는 이유**

| 이유 | 설명 |
|---|---|
| AI 생태계 | AI 회사의 SDK가 Python을 가장 먼저, 가장 충실하게 지원. Agent 도구(LangChain 등), 데이터 처리(pandas, numpy), 머신러닝(PyTorch)도 Python 중심 |
| 빠른 실험 | 코드가 짧고 문법이 간단해서 AI 기능을 빠르게 만들고 바꿔보기 좋음 |
| AI 팀과의 협업 | 데이터, AI 담당자들이 주로 Python을 사용 |

> ⚠️ "Python으로만 AI를 쓸 수 있다"는 아님. Claude API는 Java SDK도 있음.
> → "Java로도 가능하지만, AI 관련 라이브러리와 자료가 Python에 가장 풍부해서 AI 기능을 실험하고 확장하기에 유리하다고 판단했습니다."

**Python 웹 프레임워크 비교**

| | FastAPI | Django | Flask |
|---|---|---|---|
| 성격 | API 서버에 특화, 가벼움 | 다 갖춘 종합 세트 | 최소한만 있는 가벼운 틀 |
| 기본 제공 | 자동 검증(Pydantic), 자동 API 문서(Swagger), 비동기 지원 | ORM, 관리자 페이지, 로그인, 템플릿 | 라우팅 정도 |
| 장점 | 타입 기반이라 Spring 개발자에게 익숙, API 개발이 빠름 | 큰 서비스를 빠르게 갖출 수 있음 | 자유도가 높음 |
| 단점 | ORM, 인증은 직접 골라서 붙여야 함 | 무겁고, API만 만들기엔 과함 | 검증, 문서를 직접 다 붙여야 함 |

**왜 FastAPI를 골랐나**

> "이번 프로젝트는 화면 없이 API만 필요했고, Claude API와 연동하는 백엔드가 목적이었습니다. FastAPI는 타입 선언만으로 요청 검증과 API 문서가 자동으로 생겨서 Spring의 DTO와 Swagger에 익숙한 저에게 전환이 쉬웠고, AI 서비스 백엔드로도 많이 쓰여서 선택했습니다."

꼬리 질문: "비동기는 써봤어요?"
> "FastAPI가 비동기를 지원하는 건 알지만, 이번엔 이해를 우선해 동기 방식으로 구현했습니다. Claude API 호출처럼 기다리는 시간이 긴 작업이 많아지면 비동기로 바꾸는 게 다음 단계라고 생각합니다."

### B. 백엔드 기본 개념

| 개념 | 한 줄 정의 | 이 프로젝트에서 |
|---|---|---|
| REST API | URL(자원)과 HTTP 메서드(행동)로 기능을 표현하는 설계 방식 | `GET /products`, `POST /orders` |
| HTTP 메서드 | GET 조회, POST 생성, PUT 수정, DELETE 삭제 | |
| DTO | 계층 사이에서 데이터를 주고받는 객체 | Pydantic 모델 (`schemas.py`) |
| 의존성 주입 (DI) | 필요한 객체를 직접 만들지 않고 외부에서 넣어받는 것 | Spring은 Bean, FastAPI는 `Depends` |
| ORM | DB 테이블과 객체를 연결해 SQL 대신 객체로 다루는 기술 | JPA ↔ SQLAlchemy |
| 트랜잭션 | 여러 DB 작업을 묶어 전부 성공하거나 전부 취소하는 것 | 주문 여러 건을 하나로 묶고 실패 시 롤백 |
| 세션 / 영속성 컨텍스트 | 한 요청 동안 DB 작업과 객체를 관리하는 공간 | `get_db()`로 요청마다 세션 생성 |

**HTTP 상태 코드 (이 프로젝트에서 실제로 쓴 것)**

| 코드 | 뜻 | 언제 |
|---|---|---|
| 200 | 성공 | 조회, `/chat` 성공 |
| 201 | 생성 성공 | 주문 생성 |
| 400 | 잘못된 요청 | 재고 부족 |
| 404 | 없음 | 없는 상품 |
| 422 | 형식이 틀림 | 따옴표가 깨져서 실제로 겪은 에러 |
| 429 | 요청이 너무 많음 | Claude API 호출 제한 |
| 500 | 서버 내부 오류 | |
| 502 | 외부 서버 문제 | Claude API 연결 실패 |

### C. LLM / AI Agent 개념

| 개념 | 한 줄 정의 | 이 프로젝트에서 |
|---|---|---|
| LLM | 많은 글을 학습해 사람의 말을 이해하고 글을 만드는 AI 모델 | Claude |
| 토큰 | LLM이 글을 처리하는 단위. 비용과 길이 제한의 기준 | 대화가 길어질수록 비용 증가 |
| Stateless | LLM은 이전 대화를 기억하지 않음. 매번 대화 전체를 보내야 함 | `messages`를 매번 통째로 전송 |
| System Prompt | LLM의 역할과 행동 규칙을 정하는 지시문 | "추측 금지", "주문 전 확인" |
| Tool Use (Function Calling) | LLM이 외부 기능을 골라 실행을 요청하고, 실행은 우리 서버가 하는 방식 | 검색, 주문, 조회 Tool |
| JSON Schema | 데이터의 모양(항목, 타입, 필수 여부)을 정하는 표준 형식 | Tool의 `input_schema` |
| 환각 (Hallucination) | LLM이 모르는 걸 그럴듯하게 지어내는 현상 | 시나리오 2에서 지어내지 않음 |
| AI Agent | LLM이 Tool로 실제 일을 하고, 결과를 보고 다음 행동을 스스로 정하며 목표를 끝까지 처리하는 구조 | 검색 → 주문을 스스로 판단 |
| 컨텍스트 (맥락) | LLM이 판단할 때 보는 모든 정보 (대화, Tool 기록, 규칙) | 시나리오 6: Tool 기록이 빠져서 문제 |
| Human-in-the-loop | 중요한 작업은 실행 전에 사람의 확인을 받는 설계 | 시나리오 5: 주문 전 확인 |

**AI Agent란**

> 개발자가 LLM에게 행동 규칙, 도구(Tool), 반복 구조를 제공 → LLM이 스스로 판단해서 도구로 일을 수행하고, 그 결과를 보고 다음 행동을 정하며 목표를 끝까지 처리하는 것.
> 일의 순서(검색 → 주문)는 개발자가 코드로 정하지 않고 LLM이 판단한다.

**꼭 구분해서 말할 수 있어야 하는 것**

| 비교 | 차이 |
|---|---|
| 챗봇 vs Agent | 챗봇은 말로 답하고 끝남. Agent는 Tool로 실제 일을 하고 결과를 보고 다음 행동을 정함 |
| Tool Use vs Agent | Tool Use는 기능을 요청하는 기술. Agent는 그걸 반복하며 목표를 처리하는 구조 |
| 일반 지식 vs 가게 데이터 | 일반 지식은 LLM이 원래 앎(틀릴 수 있음). 가격, 재고는 Tool로 DB에서 가져와야 정확 |

### D. 안전한 Agent 설계

| 개념 | 왜 필요한가 | 이 프로젝트에서 |
|---|---|---|
| 가드레일 (안전장치) | AI 판단은 틀릴 수 있어서 | System Prompt 규칙 + 코드 검증 + 반복 제한 |
| 반복 횟수 제한 | 무한 반복, 비용 폭주 방지 | 최대 8번 |
| 에러를 결과로 전달 | Claude가 상황을 이해하고 대안을 제시하게 | `is_error: true` |
| 코드 레벨 검증 | AI가 실수해도 데이터가 망가지지 않게 | 재고 검증 + 롤백 |
| 로직 재사용 | 같은 규칙이 한 곳에만 있게 | REST API와 Tool이 같은 서비스 함수 사용 |
| 테스트에서 가짜 LLM | 비용 없이, 매번 같은 결과로 테스트 | `FakeClaude`로 반복문 검증 |
| 권한 / 인증 | 남의 정보로 주문하는 걸 막아야 함 | ⚠️ 아직 없음. 손님이 말한 이메일로 주문 → 개선 과제 |

### E. 자소서에 쓴 단어들

| 개념 | 한 줄 정의 | 이 프로젝트와 연결 |
|---|---|---|
| RAG | 질문과 관련된 문서를 먼저 찾아서 LLM에게 함께 넘겨 답하게 하는 방식. LLM이 모르는 내부 정보로 답할 때 사용 | 시나리오 4: 맛 노트 문서를 RAG로 연결하면 더 정확한 추천 가능 |
| RPA (UiPath) | 사람이 하던 반복 작업(클릭, 입력, 파일 처리)을 정해진 규칙대로 자동 실행하는 기술 | |
| RPA vs AI Agent | RPA는 규칙대로 정확히 실행하지만 판단은 못 함. Agent는 판단할 수 있지만 매번 같지는 않음 | "AI의 판단력 + RPA의 실행력 결합" |
| 호출 제한(429) / 인증 만료(401) | 외부 API의 대표적인 실패 상황 | Agent는 LLM이 Tool을 불규칙하게 많이 부르므로 더 중요 |

꼬리 질문: "RAG는 써봤어요?"
> "아직 직접 구현하지는 않았습니다. 이번 프로젝트에서 맛 정보가 없어 LLM이 일반 지식으로 추천하는 걸 보고, 정확한 정보를 주려면 RAG가 필요하다는 걸 느껴서 다음 학습 목표로 잡았습니다."

### 마지막 점검: 바로 답할 수 있게

1. Tool Use가 뭐예요? → Claude는 요청만, 실행은 서버
2. Agent랑 챗봇 차이는? → 실제 일 + 결과를 보고 다음 행동
3. Claude는 대화를 기억해요? → 아니요(stateless) → 시나리오 6으로 연결
4. 왜 FastAPI예요? → API 중심 + 타입 기반 자동 검증과 문서 + AI 생태계
5. AI가 실수하면요? → 안전장치 3겹 (주문 전 확인, 코드 검증과 롤백, 반복 제한)
6. RAG가 뭐예요? → 관련 문서를 찾아서 LLM에게 함께 넘기는 방식
7. RPA랑 Agent 차이는? → 규칙대로 실행 vs 판단
