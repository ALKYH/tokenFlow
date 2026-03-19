from pydantic import BaseModel, ConfigDict, EmailStr


class ProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    display_name: str
    bio: str
    avatar_url: str
    preferences: dict = {}
    api_provider: str | None = None
    has_api_key: bool = False
    is_active: bool


class ProfileUpdate(BaseModel):
    display_name: str
    bio: str = ''
    avatar_url: str = ''
    preferences: dict = {}
    api_provider: str | None = None
    api_key: str | None = None
