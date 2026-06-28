from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class AuthRegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)


class AuthLoginRequest(BaseModel):
    email: EmailStr
    password: str


class GoogleAuthRequest(BaseModel):
    id_token: str = Field(min_length=1)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ConversationCreateRequest(BaseModel):
    title: str | None = None


class ConversationResponse(BaseModel):
    id: str
    title: str | None
    created_at: datetime


class MessageResponse(BaseModel):
    id: str
    role: str
    content: str
    created_at: datetime


class ChatHistoryItem(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(min_length=1)


class ChatRequest(BaseModel):
    conversation_id: str | None = None
    question: str = Field(min_length=1)
    history: list[ChatHistoryItem] = Field(default_factory=list)
    use_hyde: bool = Field(default=True, description="Enable HyDE for question rewriting")


class ChunkResponse(BaseModel):
    content: str
    source: str
    score: float | None = None
    rerank_score: float | None = None
    rank: int | None = None


class EvaluateChunksResponse(BaseModel):
    question: str
    chunks: list[ChunkResponse]
    total_chunks: int


class PromptUsed(BaseModel):
    name: str
    template: str


class LLMInfo(BaseModel):
    provider: str 
    model: str     


class DetailedEvaluationResponse(BaseModel):
    question: str
    question_rewrite: str | None = None
    hyde_reformulation: str | None = None
    chunks: list[ChunkResponse] | None = None
    total_chunks: int = 0
    use_hyde: bool = True
    prompts_used: list[PromptUsed] | None = None
    answer_raw: str | None = None
    answer_formatted: str | None = None
    rewrite_llm: LLMInfo | None = None
    answer_llm: LLMInfo | None = None


class ComparisonResult(BaseModel):
    provider: str
    model: str
    answer: str
    time_ms: float
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    error: str | None = None


class ComparisonEvaluationResponse(BaseModel):
    question: str
    question_rewrite: str | None = None
    chunks: list[ChunkResponse] | None = None
    total_chunks: int = 0
    use_hyde: bool = True
    llm_result: ComparisonResult
    slm_result: ComparisonResult
    time_difference_ms: float
    faster_provider: str