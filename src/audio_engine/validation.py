"""Deterministic schema, evidence, and cross-artifact validation."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import cast
from urllib.parse import unquote, urlsplit

from pydantic import BaseModel, ValidationError

from audio_engine.artifacts import (
    ARTIFACT_CONTRACT_VERSION,
    ARTIFACT_MODELS,
    Artifact,
    ArtifactReference,
    Claim,
    EditorialPlan,
    EpisodeScript,
    EvidenceDossier,
)
from audio_engine.safety import SafetyError, resolve_within_roots

ARTIFACT_TYPES = tuple(ARTIFACT_MODELS)
_URI_SCHEME = re.compile(r"^[a-z][a-z0-9+.-]*$")
_UNSAFE_URI_SCHEMES = frozenset({"data", "file", "javascript"})


@dataclass(frozen=True, order=True)
class ValidationIssue:
    code: str
    path: str
    message: str


@dataclass(frozen=True)
class ValidationReport:
    artifact_type: str
    valid: bool
    errors: tuple[ValidationIssue, ...]
    warnings: tuple[ValidationIssue, ...]

    def to_dict(self, *, concise: bool = False) -> dict[str, object]:
        error_limit = 10 if concise else len(self.errors)
        warning_limit = 10 if concise else len(self.warnings)
        return {
            "artifact_type": self.artifact_type,
            "valid": self.valid,
            "errors": [asdict(issue) for issue in self.errors[:error_limit]],
            "warnings": [asdict(issue) for issue in self.warnings[:warning_limit]],
        }


def _pointer(parts: Sequence[str | int]) -> str:
    if not parts:
        return "/"
    escaped = [str(part).replace("~", "~0").replace("/", "~1") for part in parts]
    return "/" + "/".join(escaped)


def _issue(code: str, path: str, message: str) -> ValidationIssue:
    return ValidationIssue(code=code, path=path, message=message)


def _schema_issues(error: ValidationError) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for item in error.errors():
        location = tuple(item["loc"])
        issues.append(_issue("schema_error", _pointer(location), str(item["msg"])))
    return issues


def _unique_id_issues(
    records: Sequence[BaseModel], field_name: str, collection_path: str
) -> list[ValidationIssue]:
    seen: set[str] = set()
    issues: list[ValidationIssue] = []
    for index, record in enumerate(records):
        value = cast(str, getattr(record, field_name))
        if value in seen:
            issues.append(
                _issue(
                    "duplicate_id",
                    f"/{collection_path}/{index}/{field_name}",
                    f"{field_name} must be unique",
                )
            )
        seen.add(value)
    return issues


def _reference_type_issue(
    reference: ArtifactReference, expected: str, path: str
) -> ValidationIssue | None:
    if reference.artifact_type == expected:
        return None
    return _issue(
        "artifact_type_mismatch",
        f"{path}/artifact_type",
        f"artifact reference must have type {expected}",
    )


def _locator_issue(locator: str, allowed_input_roots: Sequence[Path]) -> str | None:
    if any(character.isspace() for character in locator) or "\x00" in locator or "\\" in locator:
        return "source locator contains whitespace, a null byte, or a backslash"
    try:
        parsed = urlsplit(locator)
    except ValueError:
        return "source locator is not a valid URI or filesystem path"
    if parsed.scheme:
        scheme = parsed.scheme.lower()
        if not _URI_SCHEME.fullmatch(scheme) or scheme in _UNSAFE_URI_SCHEMES:
            return "source locator uses an unsafe URI scheme"
        if parsed.username is not None or parsed.password is not None:
            return "source locator must not contain credentials"
        decoded_path = unquote(parsed.path)
        if "\x00" in decoded_path:
            return "source locator contains an encoded null byte"
        if ".." in decoded_path.split("/"):
            return "source locator contains path traversal"
        if scheme in {"http", "https"} and not parsed.netloc:
            return "web source locator must contain a host"
        if scheme not in {"http", "https"} and not (parsed.netloc or parsed.path):
            return "resource locator must identify a resource"
        return None
    path = Path(locator)
    if not path.is_absolute() or not allowed_input_roots:
        return "filesystem source locator requires an absolute path and an allowed input root"
    try:
        resolve_within_roots(path, allowed_input_roots, must_exist=True)
    except SafetyError as error:
        return str(error)
    return None


def _evidence_issues(
    dossier: EvidenceDossier, allowed_input_roots: Sequence[Path]
) -> tuple[list[ValidationIssue], list[ValidationIssue]]:
    errors: list[ValidationIssue] = []
    warnings: list[ValidationIssue] = []

    reference_issue = _reference_type_issue(
        dossier.collection_request, "collection-request", "/collection_request"
    )
    if reference_issue:
        errors.append(reference_issue)

    errors.extend(_unique_id_issues(dossier.candidates, "candidate_id", "candidates"))
    errors.extend(_unique_id_issues(dossier.claims, "claim_id", "claims"))
    errors.extend(_unique_id_issues(dossier.claim_supports, "support_id", "claim_supports"))
    errors.extend(_unique_id_issues(dossier.sources, "source_id", "sources"))

    candidates = {item.candidate_id: item for item in dossier.candidates}
    claims = {item.claim_id: item for item in dossier.claims}
    supports = {item.support_id: item for item in dossier.claim_supports}
    sources = {item.source_id: item for item in dossier.sources}

    if len(dossier.candidates) > dossier.limits.maximum_candidates:
        errors.append(
            _issue(
                "dossier_limit_exceeded",
                "/candidates",
                "candidate count exceeds limits.maximum_candidates",
            )
        )
    if len(dossier.sources) > dossier.limits.maximum_sources:
        errors.append(
            _issue(
                "dossier_limit_exceeded",
                "/sources",
                "source count exceeds limits.maximum_sources",
            )
        )
    if dossier.estimated_tokens > dossier.limits.maximum_estimated_tokens:
        errors.append(
            _issue(
                "dossier_limit_exceeded",
                "/estimated_tokens",
                "estimated tokens exceed limits.maximum_estimated_tokens",
            )
        )
    elif dossier.estimated_tokens >= dossier.limits.warning_estimated_tokens:
        warnings.append(
            _issue(
                "dossier_size_warning",
                "/estimated_tokens",
                "estimated tokens reached limits.warning_estimated_tokens",
            )
        )

    for candidate_index, candidate in enumerate(dossier.candidates):
        for claim_index, claim_id in enumerate(candidate.claim_ids):
            claim = claims.get(claim_id)
            path = f"/candidates/{candidate_index}/claim_ids/{claim_index}"
            if claim is None:
                errors.append(_issue("unknown_claim", path, "candidate references unknown claim"))
            elif claim.candidate_id != candidate.candidate_id:
                errors.append(
                    _issue("claim_candidate_mismatch", path, "claim belongs to another candidate")
                )
        for source_index, source_id in enumerate(candidate.source_ids):
            if source_id not in sources:
                errors.append(
                    _issue(
                        "unknown_source",
                        f"/candidates/{candidate_index}/source_ids/{source_index}",
                        "candidate references unknown source",
                    )
                )

    supports_by_claim: dict[str, list[str]] = defaultdict(list)
    for support in dossier.claim_supports:
        supports_by_claim[support.claim_id].append(support.support_id)

    for claim_index, claim in enumerate(dossier.claims):
        if claim.candidate_id not in candidates:
            errors.append(
                _issue(
                    "unknown_candidate",
                    f"/claims/{claim_index}/candidate_id",
                    "claim references unknown candidate",
                )
            )
        if not claim.support_ids or not supports_by_claim.get(claim.claim_id):
            errors.append(
                _issue(
                    "missing_support",
                    f"/claims/{claim_index}/support_ids",
                    "factual claim requires at least one claim-support record",
                )
            )
        for support_index, support_id in enumerate(claim.support_ids):
            support = supports.get(support_id)
            path = f"/claims/{claim_index}/support_ids/{support_index}"
            if support is None:
                errors.append(
                    _issue("unknown_support", path, "claim references unknown claim support")
                )
            elif support.claim_id != claim.claim_id:
                errors.append(
                    _issue("support_claim_mismatch", path, "support belongs to another claim")
                )

    for support_index, support in enumerate(dossier.claim_supports):
        claim = claims.get(support.claim_id)
        source = sources.get(support.source_id)
        if claim is None:
            errors.append(
                _issue(
                    "unknown_claim",
                    f"/claim_supports/{support_index}/claim_id",
                    "claim support references unknown claim",
                )
            )
        elif support.support_id not in claim.support_ids:
            errors.append(
                _issue(
                    "unlinked_support",
                    f"/claim_supports/{support_index}/support_id",
                    "claim support is not listed by its claim",
                )
            )
        if source is None:
            errors.append(
                _issue(
                    "unknown_source",
                    f"/claim_supports/{support_index}/source_id",
                    "claim support references unknown source",
                )
            )
        else:
            if source.access_status not in {"retrieved", "partial"}:
                errors.append(
                    _issue(
                        "unretrieved_support",
                        f"/claim_supports/{support_index}/source_id",
                        "claim support source is not retrievable",
                    )
                )
            if (
                support.source_relationship.independence_group
                != source.originality.independence_group
            ):
                errors.append(
                    _issue(
                        "source_relationship_mismatch",
                        f"/claim_supports/{support_index}/source_relationship/independence_group",
                        "support independence group must match the source",
                    )
                )
            if support.source_relationship.originality != source.originality.kind:
                errors.append(
                    _issue(
                        "source_relationship_mismatch",
                        f"/claim_supports/{support_index}/source_relationship/originality",
                        "support originality must match the source",
                    )
                )
            if claim is not None:
                candidate = candidates.get(claim.candidate_id)
                if candidate is not None and support.source_id not in candidate.source_ids:
                    errors.append(
                        _issue(
                            "candidate_source_mismatch",
                            f"/claim_supports/{support_index}/source_id",
                            "support source is not listed by the claim candidate",
                        )
                    )
        if support.evidence.excerpt is None and support.evidence.locator is None:
            errors.append(
                _issue(
                    "missing_evidence",
                    f"/claim_supports/{support_index}/evidence",
                    "claim support requires a short excerpt or precise locator",
                )
            )
        elif (
            support.evidence.excerpt is None
            and source is not None
            and source.originality.kind != "primary_source"
        ):
            errors.append(
                _issue(
                    "excerpt_required",
                    f"/claim_supports/{support_index}/evidence/excerpt",
                    "only a primary-source locator may replace a supporting excerpt",
                )
            )
        if support.support_type == "attributed" and not (
            support.required_attribution or (claim and claim.required_attribution)
        ):
            errors.append(
                _issue(
                    "missing_attribution",
                    f"/claim_supports/{support_index}/required_attribution",
                    "attributed support requires attribution text",
                )
            )
        if support.support_type == "disputed" and not support.qualifications:
            errors.append(
                _issue(
                    "missing_qualification",
                    f"/claim_supports/{support_index}/qualifications",
                    "disputed support requires qualification text",
                )
            )

    source_identity_groups: dict[tuple[str, str], set[str]] = defaultdict(set)
    source_identity_indexes: dict[tuple[str, str], list[int]] = defaultdict(list)
    for source_index, source in enumerate(dossier.sources):
        locator_problem = _locator_issue(source.canonical_locator, allowed_input_roots)
        if locator_problem:
            errors.append(
                _issue(
                    "unsafe_locator",
                    f"/sources/{source_index}/canonical_locator",
                    locator_problem,
                )
            )
        if source.content_hash is None and not source.notes:
            errors.append(
                _issue(
                    "missing_content_hash_reason",
                    f"/sources/{source_index}/notes",
                    "notes must explain why content_hash is unavailable",
                )
            )
        identities = [("locator", source.canonical_locator)]
        if source.content_hash:
            identities.append(("content_hash", source.content_hash))
        for identity in identities:
            source_identity_groups[identity].add(source.originality.independence_group)
            source_identity_indexes[identity].append(source_index)

    false_independence_indexes: set[int] = set()
    for identity, groups in source_identity_groups.items():
        if len(groups) > 1:
            false_independence_indexes.update(source_identity_indexes[identity])
    for source_index in sorted(false_independence_indexes):
        errors.append(
            _issue(
                "false_independence",
                f"/sources/{source_index}/originality/independence_group",
                "duplicate source representations must share an independence group",
            )
        )

    return errors, warnings


def validate_artifact_data(
    artifact_type: str,
    data: object,
    *,
    allowed_input_roots: Sequence[Path] = (),
) -> tuple[Artifact | None, ValidationReport]:
    """Validate decoded JSON without executing or mutating source content."""
    if artifact_type not in ARTIFACT_MODELS:
        report = ValidationReport(
            artifact_type,
            False,
            (_issue("unknown_artifact_type", "/", "artifact type is not supported"),),
            (),
        )
        return None, report
    if not isinstance(data, Mapping):
        report = ValidationReport(
            artifact_type,
            False,
            (_issue("schema_error", "/", "artifact root must be a JSON object"),),
            (),
        )
        return None, report
    mapping = cast(Mapping[str, object], data)
    version = mapping.get("contract_version")
    if version != ARTIFACT_CONTRACT_VERSION:
        report = ValidationReport(
            artifact_type,
            False,
            (
                _issue(
                    "unsupported_version",
                    "/contract_version",
                    f"supported contract version is {ARTIFACT_CONTRACT_VERSION}",
                ),
            ),
            (),
        )
        return None, report

    model = ARTIFACT_MODELS[artifact_type]
    try:
        artifact = cast(Artifact, model.model_validate(mapping))
    except ValidationError as error:
        errors = tuple(sorted(_schema_issues(error)))
        return None, ValidationReport(artifact_type, False, errors, ())

    semantic_errors: list[ValidationIssue] = []
    semantic_warnings: list[ValidationIssue] = []
    if isinstance(artifact, EvidenceDossier):
        semantic_errors, semantic_warnings = _evidence_issues(artifact, allowed_input_roots)

    errors = tuple(sorted(semantic_errors))
    warnings = tuple(sorted(semantic_warnings))
    return artifact, ValidationReport(artifact_type, not errors, errors, warnings)


def load_artifact_file(
    artifact_type: str,
    path: Path,
    *,
    allowed_input_roots: Sequence[Path] = (),
) -> tuple[Artifact | None, ValidationReport]:
    """Read one JSON artifact and return a safe machine-readable report."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        report = ValidationReport(
            artifact_type,
            False,
            (_issue("invalid_json", "/", "artifact is unreadable or is not valid JSON"),),
            (),
        )
        return None, report
    return validate_artifact_data(
        artifact_type,
        data,
        allowed_input_roots=allowed_input_roots,
    )


def validate_plan_against_dossier(
    plan: EditorialPlan, dossier: EvidenceDossier
) -> tuple[ValidationIssue, ...]:
    """Validate baseline plan references without imposing editorial policy."""
    issues: list[ValidationIssue] = []
    reference_issue = _reference_type_issue(plan.evidence_dossier, "evidence", "/evidence_dossier")
    if reference_issue:
        issues.append(reference_issue)

    candidates = {candidate.candidate_id: candidate for candidate in dossier.candidates}
    claims: dict[str, Claim] = {claim.claim_id: claim for claim in dossier.claims}
    selected: set[str] = set()
    for segment_index, segment in enumerate(plan.segments):
        candidate = candidates.get(segment.candidate_id)
        if candidate is None:
            issues.append(
                _issue(
                    "unknown_candidate",
                    f"/segments/{segment_index}/candidate_id",
                    "planned segment references unknown candidate",
                )
            )
        elif segment.candidate_id in selected:
            issues.append(
                _issue(
                    "duplicate_selection",
                    f"/segments/{segment_index}/candidate_id",
                    "candidate may be selected only once",
                )
            )
        selected.add(segment.candidate_id)
        if candidate and not candidate.source_ids:
            issues.append(
                _issue(
                    "missing_source_support",
                    f"/segments/{segment_index}/candidate_id",
                    "selected candidate must have source support",
                )
            )
        if candidate and segment.section is not None:
            candidate_section = candidate.classification.get("section")
            if isinstance(candidate_section, str) and segment.section != candidate_section:
                issues.append(
                    _issue(
                        "classification_mismatch",
                        f"/segments/{segment_index}/section",
                        "planned section does not match candidate classification",
                    )
                )
        for field_name, claim_ids in (
            ("required_claim_ids", segment.required_claim_ids),
            ("optional_claim_ids", segment.optional_claim_ids),
        ):
            for claim_index, claim_id in enumerate(claim_ids):
                claim = claims.get(claim_id)
                path = f"/segments/{segment_index}/{field_name}/{claim_index}"
                if claim is None:
                    issues.append(
                        _issue("unknown_claim", path, "planned segment references unknown claim")
                    )
                elif claim.candidate_id != segment.candidate_id:
                    issues.append(
                        _issue(
                            "claim_candidate_mismatch",
                            path,
                            "claim belongs to another candidate",
                        )
                    )
                elif not claim.support_ids:
                    issues.append(
                        _issue("missing_support", path, "planned factual claim has no support")
                    )

    excluded: set[str] = set()
    for exclusion_index, exclusion in enumerate(plan.exclusions):
        path = f"/exclusions/{exclusion_index}/candidate_id"
        if exclusion.candidate_id not in candidates:
            issues.append(
                _issue("unknown_candidate", path, "exclusion references unknown candidate")
            )
        if exclusion.candidate_id in selected:
            issues.append(
                _issue("selected_and_excluded", path, "candidate cannot be selected and excluded")
            )
        if exclusion.candidate_id in excluded:
            issues.append(
                _issue("duplicate_exclusion", path, "candidate is excluded more than once")
            )
        excluded.add(exclusion.candidate_id)
    return tuple(sorted(issues))


def validate_script_against_plan_and_dossier(
    script: EpisodeScript,
    plan: EditorialPlan,
    dossier: EvidenceDossier,
) -> tuple[ValidationIssue, ...]:
    """Validate script lineage across plan, candidate, claim, support, and source IDs."""
    issues: list[ValidationIssue] = []
    for reference, expected, path in (
        (script.evidence_dossier, "evidence", "/evidence_dossier"),
        (script.editorial_plan, "plan", "/editorial_plan"),
        (script.transcript, "transcript", "/transcript"),
    ):
        reference_issue = _reference_type_issue(reference, expected, path)
        if reference_issue:
            issues.append(reference_issue)

    planned_segments = {segment.segment_id: segment for segment in plan.segments}
    claims = {claim.claim_id: claim for claim in dossier.claims}
    candidates = {candidate.candidate_id: candidate for candidate in dossier.candidates}
    supports = {support.support_id: support for support in dossier.claim_supports}
    sources = {source.source_id: source for source in dossier.sources}

    for turn_index, turn in enumerate(script.turns):
        planned = (
            planned_segments.get(turn.planned_segment_id)
            if turn.planned_segment_id is not None
            else None
        )
        if turn.planned_segment_id is not None and planned is None:
            issues.append(
                _issue(
                    "unknown_planned_segment",
                    f"/turns/{turn_index}/planned_segment_id",
                    "script turn references unknown planned segment",
                )
            )
        if turn.candidate_id is not None and turn.candidate_id not in candidates:
            issues.append(
                _issue(
                    "unknown_candidate",
                    f"/turns/{turn_index}/candidate_id",
                    "script turn references unknown candidate",
                )
            )
        if planned and turn.candidate_id is not None and turn.candidate_id != planned.candidate_id:
            issues.append(
                _issue(
                    "plan_candidate_mismatch",
                    f"/turns/{turn_index}/candidate_id",
                    "script candidate does not match its planned segment",
                )
            )
        for claim_index, claim_id in enumerate(turn.claim_ids):
            path = f"/turns/{turn_index}/claim_ids/{claim_index}"
            claim = claims.get(claim_id)
            if claim is None:
                issues.append(_issue("unknown_claim", path, "script turn references unknown claim"))
                continue
            if turn.candidate_id is not None and claim.candidate_id != turn.candidate_id:
                issues.append(
                    _issue("claim_candidate_mismatch", path, "claim belongs to another candidate")
                )
            for support_id in claim.support_ids:
                support = supports.get(support_id)
                if support is None or support.source_id not in sources:
                    issues.append(
                        _issue(
                            "broken_claim_lineage",
                            path,
                            "claim does not resolve through support to a source",
                        )
                    )
                    break

    for segment_index, segment in enumerate(script.segments):
        for planned_index, planned_segment_id in enumerate(segment.planned_segment_ids):
            if planned_segment_id not in planned_segments:
                issues.append(
                    _issue(
                        "unknown_planned_segment",
                        f"/segments/{segment_index}/planned_segment_ids/{planned_index}",
                        "script segment references unknown planned segment",
                    )
                )
    return tuple(sorted(issues))
