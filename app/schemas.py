from pydantic import BaseModel
from typing import Optional, List

class TariffQuery(BaseModel):
    hs_code: str
    country: str

class TariffResult(BaseModel):
    hs_code: str
    country: str
    tariff_rate: float
    notes: Optional[str] = None
