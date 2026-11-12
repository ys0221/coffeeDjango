import anthropic
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.chat import agent
from app.database import get_db
from app.schemas import ChatReq, ChatRes

router = APIRouter(tags=["AI 주문 도우미"])


@router.post("/chat", response_model=ChatRes, summary="Claude와 대화하며 원두 검색/주문/조회")
def chat(
    req: ChatReq,
    db: Session = Depends(get_db),
    client: anthropic.Anthropic = Depends(agent.get_claude_client),
):
    try:
        return agent.chat(db, client, req.message, req.history)
    except anthropic.AuthenticationError:
        raise HTTPException(500, "ANTHROPIC_API_KEY가 올바르지 않습니다.")
    except TypeError as e:
        if "authentication" not in str(e):
            raise
        raise HTTPException(500, "ANTHROPIC_API_KEY 환경변수가 설정되지 않았습니다.")
    except anthropic.RateLimitError:
        raise HTTPException(429, "요청이 많아요. 잠시 후 다시 시도해 주세요.")
    except anthropic.APIStatusError as e:
        raise HTTPException(502, f"Claude API 오류: {e.status_code}")
    except anthropic.APIConnectionError:
        raise HTTPException(502, "Claude API에 연결할 수 없습니다.")
