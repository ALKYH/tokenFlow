from pydantic import BaseModel, ConfigDict, EmailStr, Field


class ApiSecretRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    provider: str
    secret_name: str
    request_prefix: str = ''
    priority: int = 100
    is_active: bool = True


class ApiSecretWrite(BaseModel):
    provider: str = 'openai'
    secret_name: str
    request_prefix: str = ''
    priority: int = 100
    api_key: str | None = None
    is_active: bool = True


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
    api_keys: list[ApiSecretRead] = Field(default_factory=list)
    default_api_name: str | None = None
    is_active: bool


class ProfileUpdate(BaseModel):
    display_name: str
    bio: str = ''
    avatar_url: str = ''
    preferences: dict = {}
    api_provider: str | None = None
    api_key: str | None = None
    api_keys: list[ApiSecretWrite] = Field(default_factory=list)
