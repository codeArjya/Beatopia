from fastapi import APIRouter, Request

from app.core.assist import run_assist
from app.models.ops import AssistRequest, AssistResponse

router = APIRouter()


@router.post("/assist", response_model=AssistResponse)
def assist(req: AssistRequest, request: Request) -> AssistResponse:
    # Sync handler (threadpool): Gemini, the DB and search_library all block.
    state = request.app.state
    return run_assist(req, getattr(state, "gemini", None), getattr(state, "pool", None), state.settings)
