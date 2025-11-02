from pydantic import BaseModel

class Asset(BaseModel):
    name: str
    price: float
    source: str