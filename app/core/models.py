from typing import Literal

from pydantic import BaseModel, Field, field_validator

Status = Literal[
    "Passed Tested Cases",
    "Counterexample Found",
    "Syntax Error",
    "Unsupported Function",
    "Reference Failure",
    "Inconclusive",
]


class GenerationEvidence(BaseModel):
    latency_seconds: float = Field(default=0, ge=0)
    usage: dict[str, int] = Field(default_factory=dict)
    estimated_cost_usd: float | None = Field(default=None, ge=0)


class EvaluationRequest(BaseModel):
    benchmark: str = Field(default="sales_total", max_length=80)
    candidate: str = "=SUM(B2:B5)"
    reference: str | None = None
    cases: int = Field(default=10, ge=2, le=200)
    seed: int = Field(default=42, ge=0, le=2**31 - 1)
    atol: float = Field(default=1e-8, ge=0, le=1)
    rtol: float = Field(default=1e-7, ge=0, le=0.1)
    minimize: bool = True
    project: str = Field(default="Default", max_length=80)
    provider: str = Field(default="manual", max_length=100)
    model: str = Field(default="manual", max_length=100)
    generation: GenerationEvidence | None = None
    upload_id: str | None = None
    sheet: str = Field(default="Data", max_length=31)
    target: str = Field(default="H2", max_length=10)
    mutation_cells: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("candidate", "reference")
    @classmethod
    def formula_size(cls, value):
        if value is not None and (len(value) > 2000 or not value.startswith("=")):
            raise ValueError("Formula must begin with = and contain at most 2000 characters")
        return value


class ProviderProfile(BaseModel):
    name: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,40}$")
    kind: Literal["openai", "anthropic", "openrouter", "ollama", "compatible", "offline"]
    base_url: str = ""
    model: str = ""
    key_env: str = Field(default="AI_API_KEY", pattern=r"^[A-Z][A-Z0-9_]{0,60}$")
    temperature: float = Field(default=0, ge=0, le=2)
    max_tokens: int = Field(default=256, ge=32, le=4096)
    timeout: float = Field(default=30, ge=1, le=120)
    request_limit: int = Field(default=20, ge=1, le=10000)
    budget_usd: float | None = Field(default=None, gt=0)
    input_per_million: float | None = Field(default=None, ge=0)
    output_per_million: float | None = Field(default=None, ge=0)
    default: bool = False
