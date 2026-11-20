"""ProductController.java 대응 — @RestController + @RequestMapping("/products")."""
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import ProductDto, ProductWriteReq, RsData
from app.services import product_service

router = APIRouter(prefix="/products", tags=["상품 API"])


@router.get("", response_model=list[ProductDto], summary="상품 다건 조회")
def get_items(db: Session = Depends(get_db)):
    return product_service.find_all(db)


@router.get("/{product_id}", response_model=ProductDto, summary="상품 단건 조회")
def get_item(product_id: int, db: Session = Depends(get_db)):
    return product_service.find_by_id(db, product_id)


@router.post("", response_model=RsData[ProductDto], status_code=status.HTTP_201_CREATED, summary="상품 생성")
def create_item(req: ProductWriteReq, db: Session = Depends(get_db)):
    # TODO: 관리자 권한 체크(rq.validateAdminActor) — 인증은 이번 범위에서 제외
    p = product_service.create(db, req.name, req.price, req.stock, req.image_url)
    return RsData(resultCode="201-1", msg=f"{p.id}번 상품이 생성되었습니다.", data=ProductDto.model_validate(p))


@router.put("/{product_id}", response_model=RsData[ProductDto], summary="상품 수정")
def modify_item(product_id: int, req: ProductWriteReq, db: Session = Depends(get_db)):
    p = product_service.find_by_id(db, product_id)
    product_service.modify(db, p, req.name, req.price, req.stock, req.image_url)
    return RsData(resultCode="200-1", msg=f"{product_id}번 상품이 수정되었습니다.", data=ProductDto.model_validate(p))


@router.delete("/{product_id}", response_model=RsData[None], summary="상품 삭제")
def delete_item(product_id: int, db: Session = Depends(get_db)):
    p = product_service.find_by_id(db, product_id)
    product_service.delete(db, p)
    return RsData(resultCode="200-1", msg=f"{product_id}번 상품이 삭제되었습니다.")
