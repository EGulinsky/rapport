from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.ai.chat import run_chat_turn
from app.ai.provider import AINotConfigured, AIRateLimited, AIToolsUnsupported, AIBadRequest
from app.auth.dependencies import get_current_user
from app.database import get_db
from app.error_keys import ErrorKey, api_error

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.get("/history", response_model=schemas.ChatHistoryResponse)
def get_history(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    rows = db.query(models.ChatMessage).order_by(models.ChatMessage.created_at.asc()).all()
    return schemas.ChatHistoryResponse(messages=rows)


@router.post("/messages", response_model=schemas.ChatSendResponse)
async def send_message(
    payload: schemas.ChatSendRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    user_row = models.ChatMessage(user_id=current_user.id, role="user", content=payload.content)
    db.add(user_row)
    db.flush()

    try:
        answer, _tools_used = await run_chat_turn(db, current_user, payload.content)
    except AINotConfigured as e:
        db.commit()  # keep the user's message visible even though the reply failed
        raise HTTPException(400, str(e))
    except AIRateLimited:
        db.commit()
        raise api_error(429, ErrorKey.AI_RATE_LIMIT, "Rate-Limit des KI-Anbieters erreicht — bitte in 30–60 Sekunden nochmal versuchen.")
    except AIToolsUnsupported as e:
        db.commit()
        raise api_error(400, ErrorKey.AI_TOOLS_UNSUPPORTED, str(e))
    except AIBadRequest as e:
        db.commit()
        raise HTTPException(400, str(e))

    assistant_row = models.ChatMessage(user_id=current_user.id, role="assistant", content=answer)
    db.add(assistant_row)
    db.commit()
    return schemas.ChatSendResponse(user_message=user_row, assistant_message=assistant_row)


@router.delete("", status_code=204)
def clear_conversation(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    # The automatic tenant filter (app/database.py) only applies to SELECTs,
    # not bulk delete/update — an explicit filter here is required, not
    # optional, or this would wipe every account's conversation.
    db.query(models.ChatMessage).filter(models.ChatMessage.user_id == current_user.id).delete()
    db.commit()
