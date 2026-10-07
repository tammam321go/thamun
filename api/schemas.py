from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

from api.reports import PATTERNS
from data.personas import CATEGORIES, MERCHANT_TYPES, OUT_TYPES, PURPOSES

PaymentType = Literal[tuple(OUT_TYPES)]
PurposeCode = Literal[tuple(PURPOSES)]
Category = Literal[tuple(CATEGORIES)]
MerchantType = Literal[tuple(MERCHANT_TYPES)]
Language = Literal["en", "bn"]
ReportPattern = Literal[PATTERNS]


def clean_label(value):
    if value is None:
        return None
    kept = "".join(ch for ch in value if ch.isalnum() or ch in " -&")
    kept = " ".join(kept.split())[:30]
    return kept or None


class CheckRequest(BaseModel):
    customer_id: str = Field(pattern=r"^[A-Z]\d{4}$")
    type: PaymentType
    counterparty: str = Field(min_length=2, max_length=24, pattern=r"^[A-Za-z0-9\-]+$")
    counterparty_name: Optional[str] = Field(default=None, max_length=60)
    merchant_type: Optional[MerchantType] = None
    amount: float = Field(gt=0, le=1_000_000)
    purpose: Optional[PurposeCode] = None
    custom_label: Optional[str] = Field(default=None, max_length=60)
    lang: Language = "en"

    @field_validator("custom_label")
    @classmethod
    def tidy(cls, value):
        return clean_label(value)


class PayRequest(BaseModel):
    customer_id: str = Field(pattern=r"^[A-Z]\d{4}$")
    check_id: str = Field(min_length=4, max_length=40)
    action: Literal["proceed", "cancel"]
    otp: Optional[str] = Field(default=None, pattern=r"^\d{4}$")


class LabelRequest(BaseModel):
    customer_id: str = Field(pattern=r"^[A-Z]\d{4}$")
    txn_id: str = Field(min_length=2, max_length=20)
    category: Optional[Category] = None
    custom_label: Optional[str] = Field(default=None, max_length=60)

    @field_validator("custom_label")
    @classmethod
    def tidy(cls, value):
        return clean_label(value)


class GoalRequest(BaseModel):
    customer_id: str = Field(pattern=r"^[A-Z]\d{4}$")
    target: float = Field(gt=0, le=10_000_000)
    months: int = Field(ge=1, le=60)
    lang: Language = "en"


class SaveRequest(BaseModel):
    customer_id: str = Field(pattern=r"^[A-Z]\d{4}$")
    amount: float = Field(gt=0, le=1_000_000)
    lang: Language = "en"


class AskRequest(BaseModel):
    customer_id: str = Field(pattern=r"^[A-Z]\d{4}$")
    question: str = Field(min_length=2, max_length=300)
    lang: Language = "en"


class ResetRequest(BaseModel):
    customer_id: Optional[str] = Field(default=None, pattern=r"^[A-Z]\d{4}$")


Answer = Literal["yes", "partly", "no"]


class SessionRequest(BaseModel):
    customer_id: Optional[str] = Field(default=None, pattern=r"^[A-Z]\d{4}$")


class FeedbackRequest(BaseModel):
    scenario: Literal["normal", "unusual", "new_recipient", "reported", "bill_risk", "overspending", "free"]
    decision: Optional[Literal["silent", "nudge", "pause"]] = None
    lang: Language = "en"
    understood_warning: Answer
    understood_reason: Answer
    intrusive: Answer
    understood_choice: Answer
    preferred_lang: Literal["bn", "en", "both"]
    comment: Optional[str] = Field(default=None, max_length=200)

    @field_validator("comment")
    @classmethod
    def tidy(cls, value):
        if value is None:
            return None
        kept = "".join(ch for ch in value if ch.isalnum() or ch in " .,!?-'")
        return " ".join(kept.split())[:200] or None


class ReportRequest(BaseModel):
    customer_id: str = Field(pattern=r"^[A-Z]\d{4}$")
    number: str = Field(min_length=4, max_length=24, pattern=r"^[A-Za-z0-9+\- ]+$")
    pattern: Optional[ReportPattern] = None
    lang: Language = "en"
