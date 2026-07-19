from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Actor:
    account_id: int
    clerk_user_id: str
    organization_id: int
    membership_id: int
    can_admin: bool
    can_teach: bool
    teacher_id: int | None
