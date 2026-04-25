from enum import Enum
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field


class ICPSegment(str, Enum):
    SEGMENT_1_FUNDED = "recently_funded_series_ab"
    SEGMENT_2_RESTRUCTURING = "midmarket_cost_restructuring"
    SEGMENT_3_LEADERSHIP_TRANSITION = "engineering_leadership_transition"
    SEGMENT_4_CAPABILITY_GAP = "specialized_capability_gap"
    NO_MATCH = "no_match"


class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class AIMaturityScore(BaseModel):
    score: int = Field(..., ge=0, le=3)
    confidence: Confidence
    signals: dict[str, str] = Field(default_factory=dict)
    justification: str = ""


class FundingEvent(BaseModel):
    round_type: str = ""
    amount_usd: Optional[float] = None
    date: Optional[str] = None
    days_ago: Optional[int] = None


class LayoffEvent(BaseModel):
    date: str = ""
    headcount_cut: Optional[int] = None
    percentage_cut: Optional[float] = None
    days_ago: Optional[int] = None


class JobPostSignal(BaseModel):
    total_open_roles: int = 0
    engineering_roles: int = 0
    ai_adjacent_roles: int = 0
    velocity_60d: Optional[float] = None  # multiplier vs 60 days ago
    sources: list[str] = Field(default_factory=list)


class LeadershipChange(BaseModel):
    role: str = ""
    name: str = ""
    date: Optional[str] = None
    days_ago: Optional[int] = None


class CompetitorGapEntry(BaseModel):
    competitor_name: str
    ai_maturity_score: int
    practices: list[str] = Field(default_factory=list)


class CompetitorGapBrief(BaseModel):
    prospect_score: int
    sector: str
    top_quartile_threshold: int
    prospect_percentile: float
    competitors: list[CompetitorGapEntry] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    confidence: Confidence = Confidence.LOW
    generated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class HiringSignalBrief(BaseModel):
    company_name: str
    crunchbase_id: str = ""
    sector: str = ""
    employee_count: Optional[int] = None
    location: str = ""
    tech_stack: list[str] = Field(default_factory=list)
    funding: Optional[FundingEvent] = None
    layoff: Optional[LayoffEvent] = None
    job_posts: Optional[JobPostSignal] = None
    leadership_change: Optional[LeadershipChange] = None
    ai_maturity: Optional[AIMaturityScore] = None
    icp_segment: ICPSegment = ICPSegment.NO_MATCH
    icp_confidence: Confidence = Confidence.LOW
    icp_reasoning: str = ""
    last_enriched_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class ProspectContact(BaseModel):
    name: str
    email: str
    phone: Optional[str] = None
    title: str = ""
    company_name: str
    company_domain: str = ""
    # filled by enrichment
    hiring_signal_brief: Optional[HiringSignalBrief] = None
    competitor_gap_brief: Optional[CompetitorGapBrief] = None
    hubspot_contact_id: Optional[str] = None
    thread_id: Optional[str] = None
    # channel state
    email_thread_active: bool = False
    sms_thread_active: bool = False
    discovery_call_booked: bool = False
    calcom_booking_uid: Optional[str] = None
    # metadata
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class OutboundEmail(BaseModel):
    to: str
    subject: str
    html_body: str
    text_body: str
    is_draft: bool = True  # all Tenacious-branded content marked draft
    variant: str = "research_grounded"  # or "generic_pitch"
    prospect_name: str = ""
    company_name: str = ""


class ConversationTurn(BaseModel):
    role: str  # "agent" or "prospect"
    channel: str  # "email" or "sms"
    content: str
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    trace_id: Optional[str] = None


class SignalResult(BaseModel):
    """
    Typed container returned by every signal module in agent/signals/.

    Every signal in the merged HiringSignalBrief must be traceable to a
    SignalResult so reviewers can verify timestamp, source, and confidence
    without reading the raw signal module code.

    Fields:
        signal_type   — one of: crunchbase_funding, layoffs_fyi, job_posts,
                        leadership_change
        company_name  — the company this result applies to
        timestamp_utc — ISO 8601 UTC at moment of acquisition
        source        — URL or file path used to produce this result
        confidence    — HIGH / MEDIUM / LOW
        data          — signal-specific payload (FundingEvent, LayoffEvent, etc.)
        error         — non-empty when acquisition failed; empty on success
    """
    signal_type: str
    company_name: str
    timestamp_utc: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    source: str = ""
    confidence: Confidence = Confidence.LOW
    data: dict = Field(default_factory=dict)
    error: str = ""
