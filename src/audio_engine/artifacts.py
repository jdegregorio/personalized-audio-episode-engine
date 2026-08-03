"""Versioned, topic-generic artifact contracts for the episode pipeline."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import PurePosixPath
from typing import Annotated, Literal, Self

from pydantic import (
    AwareDatetime,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    HttpUrl,
    JsonValue,
    field_validator,
    model_validator,
)

ARTIFACT_CONTRACT_VERSION = "1.0"


def _require_date_input(value: object) -> object:
    if isinstance(value, datetime) or not isinstance(value, (str, date)):
        raise ValueError("date must be an ISO string or date value")
    return value


def _require_datetime_input(value: object) -> object:
    if not isinstance(value, (str, datetime)):
        raise ValueError("datetime must be an ISO string or datetime value")
    return value


Identifier = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]*$", max_length=80)]
Version = Annotated[str, Field(pattern=r"^\d+\.\d+(?:\.\d+)?$", max_length=40)]
JsonDate = Annotated[date, BeforeValidator(_require_date_input), Field(strict=False)]
JsonAwareDatetime = Annotated[
    AwareDatetime,
    BeforeValidator(_require_datetime_input),
    Field(strict=False),
]
ShortText = Annotated[str, Field(min_length=1, max_length=500)]
LongText = Annotated[str, Field(min_length=1, max_length=10_000)]
Sha256 = Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
RunId = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$")]
EpisodeKey = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]*:\d{4}-\d{2}-\d{2}$")]
CandidateId = Annotated[str, Field(pattern=r"^item_[A-Za-z0-9][A-Za-z0-9_-]*$")]
ClaimId = Annotated[str, Field(pattern=r"^claim_[A-Za-z0-9][A-Za-z0-9_-]*$")]
SupportId = Annotated[str, Field(pattern=r"^support_[A-Za-z0-9][A-Za-z0-9_-]*$")]
SourceId = Annotated[str, Field(pattern=r"^source_[A-Za-z0-9][A-Za-z0-9_-]*$")]
PlanSegmentId = Annotated[str, Field(pattern=r"^segment_[A-Za-z0-9][A-Za-z0-9_-]*$")]
TurnId = Annotated[str, Field(pattern=r"^turn_[A-Za-z0-9][A-Za-z0-9_-]*$")]
TtsSegmentId = Annotated[str, Field(pattern=r"^tts_[A-Za-z0-9][A-Za-z0-9_-]*$")]


def _validate_safe_artifact_path(value: str) -> str:
    if (
        not value
        or len(value) > 1_000
        or "\x00" in value
        or "\\" in value
        or "//" in value
        or value.startswith("~")
        or value.endswith("/")
        or any(part in {"", ".", ".."} for part in value.split("/") if part != "")
    ):
        raise ValueError("artifact path must be normalized and traversal-free")
    return value


class _ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ArtifactReference(_ContractModel):
    artifact_type: Identifier
    path: str
    sha256: Sha256

    @field_validator("path")
    @classmethod
    def safe_path(cls, value: str) -> str:
        return _validate_safe_artifact_path(value)


class RequestScope(_ContractModel):
    sections: Annotated[list[Identifier], Field(min_length=1, max_length=100)]
    notes: ShortText

    @field_validator("sections")
    @classmethod
    def unique_sections(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("scope sections must be unique")
        return value


class RequestTimeWindow(_ContractModel):
    hours: Annotated[int, Field(ge=1, le=24 * 14)]


class SourcePolicy(_ContractModel):
    prefer_primary: bool
    preferred_publishers: Annotated[list[ShortText], Field(max_length=100)]
    multiple_sources_for_consequential_claims: bool
    policy: dict[Identifier, JsonValue] = Field(default_factory=dict)


class CollectionAudience(_ContractModel):
    locale: ShortText
    knowledge_level: Identifier
    preferences: Annotated[list[LongText], Field(max_length=100)]


class CollectionEditorialPriorities(_ContractModel):
    exclusions: Annotated[list[LongText], Field(max_length=100)]
    policy: dict[Identifier, JsonValue] = Field(default_factory=dict)


class CollectionTargets(_ContractModel):
    by_section: dict[Identifier, Annotated[int, Field(ge=0, le=1_000)]]
    maximum_candidates: Annotated[int, Field(ge=1, le=5_000)]
    maximum_sources: Annotated[int, Field(ge=1, le=10_000)]


class CollectionRequest(_ContractModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "urn:personalized-audio-episode-engine:schema:collection-request:1.0",
        },
    )

    contract_version: Literal["1.0"]
    prompt_version: Version | None
    created_at: JsonAwareDatetime
    run_id: RunId
    profile_id: Identifier
    episode_date: JsonDate
    timezone: ShortText
    topic: LongText
    scope: RequestScope
    audience: CollectionAudience
    editorial_priorities: CollectionEditorialPriorities
    time_window: RequestTimeWindow
    source_types: Annotated[list[Identifier], Field(min_length=1, max_length=50)]
    suggested_capabilities: Annotated[list[Identifier], Field(max_length=50)]
    allow_native_research_fallback: bool
    evidence_contract_version: Literal["1.0"]
    source_policy: SourcePolicy
    targets: CollectionTargets
    output_path: str

    @field_validator("output_path")
    @classmethod
    def safe_absolute_output(cls, value: str) -> str:
        safe = _validate_safe_artifact_path(value)
        if not PurePosixPath(safe).is_absolute():
            raise ValueError("collection output_path must be absolute")
        return safe

    @model_validator(mode="after")
    def valid_section_targets(self) -> Self:
        unknown = sorted(set(self.targets.by_section) - set(self.scope.sections))
        if unknown:
            raise ValueError(f"target sections are not declared in scope: {unknown}")
        return self


class CollectionMethod(_ContractModel):
    type: Identifier
    name: ShortText
    version: Version | None


class SourceDifferences(_ContractModel):
    baseline_consensus: LongText
    meaningful_differences: Annotated[list[LongText], Field(max_length=100)]


class Candidate(_ContractModel):
    candidate_id: CandidateId
    title: ShortText
    classification: dict[Identifier, JsonValue] = Field(default_factory=dict)
    relevant_times: dict[Identifier, JsonAwareDatetime | None] = Field(default_factory=dict)
    summary: LongText
    context: LongText
    why_it_matters: LongText
    uncertainties: Annotated[list[LongText], Field(max_length=100)]
    source_differences: SourceDifferences
    claim_ids: Annotated[list[ClaimId], Field(max_length=1_000)]
    source_ids: Annotated[list[SourceId], Field(max_length=1_000)]


class Claim(_ContractModel):
    claim_id: ClaimId
    candidate_id: CandidateId
    text: LongText
    status: Literal["confirmed", "reported", "alleged", "inferred", "disputed", "uncertain"]
    confidence: Literal["high", "medium", "low"]
    support_ids: Annotated[list[SupportId], Field(max_length=1_000)]
    required_attribution: ShortText | None
    qualifications: Annotated[list[LongText], Field(max_length=100)]


class SupportEvidence(_ContractModel):
    excerpt: Annotated[str, Field(min_length=1, max_length=1_000)] | None
    locator: ShortText | None


class SourceRelationship(_ContractModel):
    originality: Literal[
        "original_reporting", "syndicated", "aggregation", "primary_source", "unknown"
    ]
    independence_group: Identifier


class ClaimSupport(_ContractModel):
    support_id: SupportId
    claim_id: ClaimId
    source_id: SourceId
    support_type: Literal["direct", "attributed", "inferred", "disputed"]
    evidence: SupportEvidence
    required_attribution: ShortText | None
    qualifications: Annotated[list[LongText], Field(max_length=100)]
    source_relationship: SourceRelationship


class SourceOriginality(_ContractModel):
    kind: Literal["original_reporting", "syndicated", "aggregation", "primary_source", "unknown"]
    independence_group: Identifier


class EvidenceSource(_ContractModel):
    source_id: SourceId
    source_type: Identifier
    creator_or_publisher: ShortText
    title: ShortText
    canonical_locator: Annotated[str, Field(min_length=1, max_length=2_000)]
    access_status: Literal["retrieved", "partial", "unavailable", "access_denied"]
    retrieved_at: JsonAwareDatetime
    created_at: JsonAwareDatetime | None
    published_at: JsonAwareDatetime | None
    updated_at: JsonAwareDatetime | None
    content_hash: Sha256 | None
    is_primary: bool
    originality: SourceOriginality
    notes: Annotated[str, Field(max_length=2_000)] | None

    @model_validator(mode="after")
    def consistent_primary_classification(self) -> Self:
        classified_primary = self.originality.kind == "primary_source"
        if self.is_primary != classified_primary:
            raise ValueError("is_primary must agree with originality.kind")
        return self


class DossierLimits(_ContractModel):
    maximum_candidates: Annotated[int, Field(ge=1, le=5_000)] = 40
    maximum_sources: Annotated[int, Field(ge=1, le=10_000)] = 100
    warning_estimated_tokens: Annotated[int, Field(ge=1, le=1_000_000)] = 50_000
    maximum_estimated_tokens: Annotated[int, Field(ge=1, le=2_000_000)] = 100_000

    @model_validator(mode="after")
    def ordered_token_limits(self) -> Self:
        if self.warning_estimated_tokens > self.maximum_estimated_tokens:
            raise ValueError("warning_estimated_tokens must not exceed maximum_estimated_tokens")
        return self


class EvidenceDossier(_ContractModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "urn:personalized-audio-episode-engine:schema:evidence-dossier:1.0",
        },
    )

    contract_version: Literal["1.0"]
    prompt_version: Version
    collection_request: ArtifactReference
    collection_method: CollectionMethod
    collection_started_at: JsonAwareDatetime
    collection_completed_at: JsonAwareDatetime
    estimated_tokens: Annotated[int, Field(ge=0, le=2_000_000)]
    limits: DossierLimits
    candidates: Annotated[list[Candidate], Field(max_length=5_000)]
    claims: Annotated[list[Claim], Field(max_length=10_000)]
    claim_supports: Annotated[list[ClaimSupport], Field(max_length=20_000)]
    sources: Annotated[list[EvidenceSource], Field(max_length=10_000)]
    collection_notes: Annotated[list[LongText], Field(max_length=500)]
    warnings: Annotated[list[LongText], Field(max_length=500)]

    @model_validator(mode="after")
    def ordered_collection_times(self) -> Self:
        if self.collection_completed_at < self.collection_started_at:
            raise ValueError("collection_completed_at must not precede collection_started_at")
        return self


class PlannedSegment(_ContractModel):
    segment_id: PlanSegmentId
    order: Annotated[int, Field(ge=1, le=1_000)]
    candidate_id: CandidateId
    section: Identifier | None
    editorial_angle: LongText
    why_it_matters: LongText
    required_claim_ids: Annotated[list[ClaimId], Field(min_length=1, max_length=1_000)]
    optional_claim_ids: Annotated[list[ClaimId], Field(max_length=1_000)]
    desired_duration_seconds: Annotated[int, Field(ge=1, le=60 * 60)]
    lead_host: ShortText
    host_dynamic: LongText
    source_conflict_notes: Annotated[list[LongText], Field(max_length=100)]
    transition_intent: LongText


class ExcludedCandidate(_ContractModel):
    candidate_id: CandidateId
    reason_code: Identifier
    reason: ShortText


class EditorialPlan(_ContractModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "urn:personalized-audio-episode-engine:schema:editorial-plan:1.0",
        },
    )

    contract_version: Literal["1.0"]
    prompt_version: Version
    created_at: JsonAwareDatetime
    run_id: RunId
    profile_id: Identifier
    episode_date: JsonDate
    evidence_dossier: ArtifactReference
    opening_approach: LongText
    segments: Annotated[list[PlannedSegment], Field(min_length=1, max_length=100)]
    exclusions: Annotated[list[ExcludedCandidate], Field(max_length=5_000)]
    closing_takeaway: LongText
    planned_duration_seconds: Annotated[int, Field(ge=1, le=60 * 60 * 3)]

    @model_validator(mode="after")
    def consistent_segments(self) -> Self:
        segment_ids = [segment.segment_id for segment in self.segments]
        orders = [segment.order for segment in self.segments]
        if len(segment_ids) != len(set(segment_ids)):
            raise ValueError("planned segment IDs must be unique")
        if sorted(orders) != list(range(1, len(orders) + 1)):
            raise ValueError("planned segment order must be contiguous from 1")
        if sum(segment.desired_duration_seconds for segment in self.segments) != (
            self.planned_duration_seconds
        ):
            raise ValueError("planned_duration_seconds must equal segment durations")
        return self


class ScriptSpeaker(_ContractModel):
    name: ShortText
    voice: ShortText


class ScriptTurn(_ContractModel):
    turn_id: TurnId
    speaker: ShortText
    text: LongText
    turn_type: Literal["fact", "analysis", "question", "reaction", "transition", "intro", "outro"]
    claim_ids: Annotated[list[ClaimId], Field(max_length=1_000)]
    candidate_id: CandidateId | None
    planned_segment_id: PlanSegmentId | None
    performance_cue: ShortText | None


class ScriptSegment(_ContractModel):
    segment_id: TtsSegmentId
    order: Annotated[int, Field(ge=1, le=1_000)]
    planned_segment_ids: Annotated[list[PlanSegmentId], Field(max_length=100)]
    turn_ids: Annotated[list[TurnId], Field(min_length=1, max_length=5_000)]
    estimated_input_tokens: Annotated[int, Field(ge=1, le=100_000)]


class EpisodeScript(_ContractModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "urn:personalized-audio-episode-engine:schema:episode-script:1.0",
        },
    )

    contract_version: Literal["1.0"]
    prompt_version: Version
    created_at: JsonAwareDatetime
    run_id: RunId
    profile_id: Identifier
    episode_date: JsonDate
    evidence_dossier: ArtifactReference
    editorial_plan: ArtifactReference
    transcript: ArtifactReference
    speakers: Annotated[list[ScriptSpeaker], Field(min_length=2, max_length=2)]
    safe_input_tokens: Annotated[int, Field(ge=1, le=100_000)]
    estimated_duration_seconds: Annotated[int, Field(ge=1, le=60 * 60 * 3)]
    turns: Annotated[list[ScriptTurn], Field(min_length=1, max_length=10_000)]
    segments: Annotated[list[ScriptSegment], Field(min_length=1, max_length=1_000)]

    @model_validator(mode="after")
    def consistent_structure(self) -> Self:
        speaker_names = [speaker.name for speaker in self.speakers]
        if len(speaker_names) != len(set(speaker_names)):
            raise ValueError("script speakers must be unique")
        invalid_speakers = sorted({turn.speaker for turn in self.turns} - set(speaker_names))
        if invalid_speakers:
            raise ValueError(f"turns use unconfigured speakers: {invalid_speakers}")
        turn_ids = [turn.turn_id for turn in self.turns]
        if len(turn_ids) != len(set(turn_ids)):
            raise ValueError("script turn IDs must be unique")
        segment_ids = [segment.segment_id for segment in self.segments]
        orders = [segment.order for segment in self.segments]
        if len(segment_ids) != len(set(segment_ids)):
            raise ValueError("script segment IDs must be unique")
        if sorted(orders) != list(range(1, len(orders) + 1)):
            raise ValueError("script segment order must be contiguous from 1")
        assigned_turn_ids = [turn_id for segment in self.segments for turn_id in segment.turn_ids]
        if sorted(assigned_turn_ids) != sorted(turn_ids):
            raise ValueError("every script turn must appear in exactly one segment")
        if any(
            segment.estimated_input_tokens > self.safe_input_tokens for segment in self.segments
        ):
            raise ValueError("script segment exceeds safe_input_tokens")
        if any(turn.turn_type == "fact" and not turn.claim_ids for turn in self.turns):
            raise ValueError("factual turns must reference at least one claim")
        return self


class PublishedAsset(_ContractModel):
    kind: Literal["audio", "transcript", "show_notes", "episode_metadata"]
    object_key: str
    public_url: HttpUrl
    media_type: ShortText
    bytes: Annotated[int, Field(ge=1)]
    sha256: Sha256

    @field_validator("object_key")
    @classmethod
    def safe_object_key(cls, value: str) -> str:
        if (
            not value
            or value.startswith("/")
            or "\\" in value
            or "//" in value
            or any(part in {"", ".", ".."} for part in value.split("/"))
        ):
            raise ValueError("published object key must be normalized and traversal-free")
        return value

    @field_validator("public_url")
    @classmethod
    def https_public_url(cls, value: HttpUrl) -> HttpUrl:
        if value.scheme != "https":
            raise ValueError("published public URL must use HTTPS")
        return value


class PublishedEpisode(_ContractModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "urn:personalized-audio-episode-engine:schema:published-episode:1.0",
        },
    )

    contract_version: Literal["1.0"]
    prompt_version: None
    run_id: RunId
    episode_key: EpisodeKey
    profile_id: Identifier
    episode_date: JsonDate
    guid: ShortText
    title: ShortText
    description: LongText
    published_at: JsonAwareDatetime
    status: Literal["published"]
    episode_script: ArtifactReference
    audio: ArtifactReference
    transcript: ArtifactReference
    show_notes: ArtifactReference
    duration_seconds: Annotated[int, Field(ge=1, le=60 * 60 * 3)]
    enclosure_bytes: Annotated[int, Field(ge=1)]
    enclosure_media_type: Literal["audio/mpeg"]
    assets: Annotated[list[PublishedAsset], Field(min_length=4, max_length=4)]

    @model_validator(mode="after")
    def unique_asset_kinds(self) -> Self:
        kinds = [asset.kind for asset in self.assets]
        if len(kinds) != len(set(kinds)):
            raise ValueError("published asset kinds must be unique")
        return self


RunStage = Literal[
    "initialized",
    "collection",
    "editorial",
    "script",
    "tts",
    "audio",
    "publication",
    "finalized",
]


class RunFailure(_ContractModel):
    stage: RunStage
    code: Identifier
    message: ShortText
    recovery_guidance: LongText


class FinalAudioValidation(_ContractModel):
    status: Literal["pending", "valid", "invalid"]
    artifact: ArtifactReference | None
    duration_seconds: Annotated[int, Field(ge=1, le=60 * 60 * 3)] | None
    message: ShortText | None


class PublicationState(_ContractModel):
    status: Literal["not_started", "deferred", "published", "failed"]
    redacted_locations: Annotated[list[ShortText], Field(max_length=20)]
    message: ShortText | None


class RunState(_ContractModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "urn:personalized-audio-episode-engine:schema:run-state:1.0",
        },
    )

    contract_version: Literal["1.0"]
    prompt_version: None
    run_id: RunId
    episode_key: EpisodeKey
    profile_id: Identifier
    profile_version: Version
    engine_git_commit: Annotated[str, Field(pattern=r"^[0-9a-f]{7,40}$")]
    skill_version: Version
    prompt_versions: dict[Identifier, Version]
    collection_method: CollectionMethod | None
    codex_model: ShortText | None
    gemini_model: ShortText | None
    started_at: JsonAwareDatetime
    completed_at: JsonAwareDatetime | None
    current_stage: RunStage
    last_completed_valid_stage: RunStage | None
    status: Literal["running", "failed", "completed", "no_op"]
    failure: RunFailure | None
    artifacts: dict[Identifier, ArtifactReference]
    final_audio_validation: FinalAudioValidation
    publication: PublicationState

    @model_validator(mode="after")
    def consistent_terminal_state(self) -> Self:
        if self.status == "failed" and self.failure is None:
            raise ValueError("failed run state requires failure details")
        if self.status != "failed" and self.failure is not None:
            raise ValueError("only failed run state may contain failure details")
        if self.status in {"completed", "no_op"} and self.completed_at is None:
            raise ValueError("terminal run state requires completed_at")
        if self.completed_at is not None and self.completed_at < self.started_at:
            raise ValueError("completed_at must not precede started_at")
        return self


Artifact = (
    CollectionRequest
    | EvidenceDossier
    | EditorialPlan
    | EpisodeScript
    | PublishedEpisode
    | RunState
)

ARTIFACT_MODELS: dict[str, type[_ContractModel]] = {
    "collection-request": CollectionRequest,
    "evidence": EvidenceDossier,
    "plan": EditorialPlan,
    "script": EpisodeScript,
    "published-episode": PublishedEpisode,
    "run-state": RunState,
}

ARTIFACT_SCHEMA_FILENAMES: dict[str, str] = {
    "collection-request": "collection-request-v1.0.schema.json",
    "evidence": "evidence-dossier-v1.0.schema.json",
    "plan": "editorial-plan-v1.0.schema.json",
    "script": "episode-script-v1.0.schema.json",
    "published-episode": "published-episode-v1.0.schema.json",
    "run-state": "run-state-v1.0.schema.json",
}


def artifact_json_schemas() -> dict[str, dict[str, object]]:
    """Return canonical JSON Schemas keyed by public artifact type."""
    return {
        artifact_type: model.model_json_schema() for artifact_type, model in ARTIFACT_MODELS.items()
    }
