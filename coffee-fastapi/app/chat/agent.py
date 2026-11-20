"""/chat 엔드포인트가 사용하는 Tool Use 루프.

흐름
1) 사용자 메시지 + TOOLS 를 Claude에게 보냄
2) stop_reason == "tool_use" 이면 응답 안의 tool_use 블록들을 run_tool()로 실행
3) 결과를 tool_result 로 묶어 한 번의 user 메시지로 되돌려 보냄 → 다시 1)
4) Claude가 더 이상 Tool을 호출하지 않으면(end_turn) 최종 텍스트를 반환

SDK의 Tool Runner(client.beta.messages.tool_runner) 대신 루프를 직접 작성한 이유:
- 요청마다 열린 DB 세션을 Tool 실행에 그대로 넘기기 쉽고
- 어떤 Tool이 어떤 입력으로 호출됐는지 응답(tool_calls)에 담아 보여주기 위해서입니다.
"""
import os
from typing import Any

import anthropic
from sqlalchemy.orm import Session

from app.chat.tools import TOOLS, run_tool
from app.schemas import ChatMessage, ChatRes, ToolCallLog

MODEL = os.getenv("CLAUDE_MODEL", "claude-opus-5-5")
# 짧은 대화형 응답이 대부분이라 low로 시작. 품질이 부족하면 medium/high로 올려보세요.
EFFORT = os.getenv("CLAUDE_EFFORT", "low")
MAX_TOOL_ROUNDS = 8  # 무한 루프 방지

SYSTEM_PROMPT = """당신은 로컬 카페 'Grids & Circles'의 온라인 원두 주문 도우미입니다.
고객이 원두를 고르고, 주문하고, 주문 내역을 확인하도록 돕습니다.

- 상품 정보(이름, 가격, 재고, id)는 기억이나 추측으로 말하지 말고 search_products로 확인하세요.
- 주문은 실제로 재고가 차감되는 작업입니다. create_order를 호출하기 전에 고객 이메일, 상품, 수량, 총액을
  고객에게 보여주고 명시적으로 "네/주문해줘" 같은 확인을 받으세요. 확인 없이 주문하지 마세요.
- 이메일을 모르면 고객에게 물어보세요. 이메일을 지어내지 마세요.
- 매일 오후 2시 이전 주문은 당일 배송, 이후 주문은 다음 날 배송이 시작됩니다.
- Tool이 에러를 돌려주면 그 이유를 고객에게 쉽게 설명하고 대안을 제시하세요.
- 한국어로 짧고 친절하게 답하세요."""

_client: anthropic.Anthropic | None = None


def get_claude_client() -> anthropic.Anthropic:
    """FastAPI 의존성. 테스트에서는 app.dependency_overrides로 가짜 클라이언트를 주입합니다."""
    global _client
    if _client is None:
        _client = anthropic.Anthropic()  # ANTHROPIC_API_KEY 환경변수 사용
    return _client


def chat(db: Session, client: anthropic.Anthropic, message: str, history: list[ChatMessage]) -> ChatRes:
    messages: list[dict[str, Any]] = [{"role": m.role, "content": m.content} for m in history]
    messages.append({"role": "user", "content": message})
    tool_calls: list[ToolCallLog] = []

    for _ in range(MAX_TOOL_ROUNDS):
        response = client.beta.messages.create(
            model=MODEL,
            max_tokens=16000,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
            output_config={"effort": EFFORT},
            # 안전 분류기가 요청을 거절(refusal)하면 서버가 대체 모델로 자동 재시도
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )

        if response.stop_reason == "refusal":
            return ChatRes(reply="죄송해요, 이 요청은 처리할 수 없어요.", tool_calls=tool_calls)

        if response.stop_reason == "pause_turn":
            messages.append({"role": "assistant", "content": response.content})
            continue

        tool_uses = [b for b in response.content if b.type == "tool_use"]
        if response.stop_reason != "tool_use" or not tool_uses:
            # end_turn / max_tokens 등: 최종 답변
            reply = "".join(b.text for b in response.content if b.type == "text").strip()
            return ChatRes(reply=reply or "(응답이 비어 있습니다)", tool_calls=tool_calls)

        # assistant 응답은 text만이 아니라 content 전체(thinking, tool_use 포함)를 그대로 다시 넣어야 함
        messages.append({"role": "assistant", "content": response.content})

        tool_results = []
        for block in tool_uses:
            output, is_error = run_tool(db, block.name, block.input)
            tool_calls.append(ToolCallLog(name=block.name, input=block.input, output=output, is_error=is_error))
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": output,
                "is_error": is_error,
            })
        # 여러 tool 결과는 반드시 하나의 user 메시지에 모아서 보냄
        messages.append({"role": "user", "content": tool_results})

    return ChatRes(reply="요청을 처리하는 데 너무 많은 단계가 필요했어요. 조금 더 구체적으로 말씀해 주세요.",
                   tool_calls=tool_calls)
