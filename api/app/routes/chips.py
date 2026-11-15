from fastapi import APIRouter, Request

from app.core.chips import load_chips
from app.models.api import ChipsResponse

router = APIRouter()


@router.get("/chips", response_model=ChipsResponse)
def chips(request: Request) -> ChipsResponse:
    return load_chips(request.app.state.settings.vocab_path)
