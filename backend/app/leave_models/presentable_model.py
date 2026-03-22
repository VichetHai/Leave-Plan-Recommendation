import uuid

from sqlmodel import SQLModel


class UserPresentable(SQLModel):
    id: uuid.UUID
    full_name: str | None
    email: str

class TeamPresentable(SQLModel):
    id: uuid.UUID
    name: str
    team_owner: UserPresentable | None

class LeaveTypePresentable(SQLModel):
    id: uuid.UUID
    code: str
    name: str
