from pydantic import BaseModel
from typing import Optional, Dict, Any


class UserCreate(BaseModel):
    username: str
    email: str
    password: str


class UserLogin(BaseModel):
    username: str
    password: str


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str
    user: Dict[str, Any]


class TokenData(BaseModel):
    username: Optional[str] = None