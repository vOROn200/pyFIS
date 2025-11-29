from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime


class AlternateCommand(BaseModel):
    address: int
    type_code: int
    data: List[int] = Field(default_factory=list)


class PixelData(BaseModel):
    row: int
    col: int
    type_code: int
    address: int
    bit_index: int = -1  # 0..155
    generated_command: List[int]
    assigned_command: List[int]
    status: str = "unknown"  # unknown, tested_ok, tested_fail
    last_tested_at: Optional[str] = None
    notes: str = ""
    remap_commands: List[AlternateCommand] = Field(default_factory=list)
    remap_active: bool = False


class SegmentMapping(BaseModel):
    version: int = 1
    segment_name: str
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    pixels: List[PixelData] = []
