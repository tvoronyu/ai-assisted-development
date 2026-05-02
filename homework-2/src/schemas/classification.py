from pydantic import BaseModel, Field

from src.models.enums import Category, Priority


class ClassificationResult(BaseModel):
    category: Category
    priority: Priority
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str
    keywords_found: list[str] = Field(default_factory=list)
