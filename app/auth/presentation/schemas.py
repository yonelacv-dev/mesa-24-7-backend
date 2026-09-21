from pydantic import BaseModel, Field


class LoginIn(BaseModel):
    username: str = Field(max_length=64)
    password: str = Field(max_length=200)


class SessionVenueOut(BaseModel):
    slug: str
    name: str


class SessionUserOut(BaseModel):
    id: int
    username: str
    venue: SessionVenueOut


class LoginOut(BaseModel):
    token: str
    user: SessionUserOut
