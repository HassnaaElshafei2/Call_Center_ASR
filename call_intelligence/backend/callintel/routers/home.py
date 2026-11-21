"""Home: what happened recently and what needs the user today; and Ask Sia's contextual suggestions."""
from fastapi import APIRouter, Depends, Query

from ..deps import Ctx, ctx
from ..services import insights

router = APIRouter(prefix="/api/e/{ent}")


@router.get("/home")
def home(c: Ctx = Depends(ctx)):
    return insights.home(c)


@router.get("/assistant/suggestions")
def suggestions(lang: str = Query("en", pattern="^(en|ar)$"), c: Ctx = Depends(ctx)):
    return {"suggested": insights.suggestions(c, lang), "topics": insights.TOPICS[lang]}
