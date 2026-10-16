from typing import Any, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from dependencies import get_current_user
from agent.core.token_pool import token_pool

router = APIRouter(prefix="/api/admin", tags=["admin"])

def require_admin(user: dict = Depends(get_current_user)):
    if user.get("role") != "admin" and user.get("user_id") != "dev":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user

class AddTokenRequest(BaseModel):
    provider: str
    key: str

@router.get("/tokens", response_model=List[dict])
async def list_tokens(admin: dict = Depends(require_admin)):
    """List all tokens in the pool (masked)."""
    return token_pool.get_all_tokens()

@router.post("/tokens")
async def add_token(req: AddTokenRequest, admin: dict = Depends(require_admin)):
    """Add a new API token to the pool."""
    token_id = await token_pool.add_token(req.provider, req.key)
    return {"status": "ok", "id": token_id}

@router.delete("/tokens/{token_id}")
async def delete_token(token_id: str, admin: dict = Depends(require_admin)):
    """Remove a token from the pool."""
    deleted = await token_pool.delete_token(token_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Token not found")
    return {"status": "ok"}
