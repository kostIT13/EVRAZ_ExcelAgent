from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional


class ParsedCell(BaseModel):
    row: int
    col: int
    value: Any
    col_name: Optional[str] = None
    sheet_name: str


class ParsedHeader(BaseModel):
    levels: List[str] = Field(default_factory=list)
    full_name: str = ""
    col_index: int
    col_name: str


class ParsedSheet(BaseModel):
    sheet_name: str
    sheet_index: int
    headers: List[ParsedHeader]
    data: List[Dict[str, Any]]      
    cells: List[ParsedCell] = Field(default_factory=list)  
    raw_data: List[List[Any]] = Field(default_factory=list) 
    header_rows: int = 3           

    @property
    def row_count(self) -> int:
        return len(self.data)

    @property
    def col_count(self) -> int:
        return len(self.headers)


class ParsedFile(BaseModel):
    filename: str
    file_hash: str
    sheets: List[ParsedSheet]
    total_rows: int = 0
    total_cells: int = 0

    @property
    def total_sheets(self) -> int:
        return len(self.sheets)