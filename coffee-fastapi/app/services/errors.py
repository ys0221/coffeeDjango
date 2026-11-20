class NotFoundError(Exception):
    """NoSuchElementException 대응 → 404"""


class BusinessError(Exception):
    """IllegalArgumentException(재고 부족 등) 대응 → 400"""
