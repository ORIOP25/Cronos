from pydantic import BaseModel
from typing import Optional, Any


class ClerkWebhookEvent(BaseModel):
    type: str
    data: dict[str, Any]
    object: str = "event"
    timestamp: int
    instance_id: Optional[str] = None


class ClerkUserData(BaseModel):
    id: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email_addresses: list[dict[str, Any]] = []
    created_at: Optional[int] = None
    public_metadata: dict[str, Any] = {}
    unsafe_metadata: dict[str, Any] = {}


class ClerkOrganizationData(BaseModel):
    id: str
    name: str
    slug: str
    created_at: Optional[int] = None
    public_metadata: dict[str, Any] = {}


class ClerkMembershipData(BaseModel):
    role: str
    organization: dict[str, Any]
    public_metadata: dict[str, Any] = {}
    public_user_data: dict[str, Any] = {}
    created_at: Optional[int] = None
