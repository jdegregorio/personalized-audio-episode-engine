"""Deterministic episode assets, RSS merge, and safe publication orchestration."""

from __future__ import annotations

import hashlib
import html
import threading
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from email.utils import format_datetime, parsedate_to_datetime
from pathlib import Path
from typing import Literal, Protocol, cast
from urllib.parse import quote, urlsplit

from audio_engine.artifacts import (
    ArtifactReference,
    EditorialPlan,
    EvidenceDossier,
    FinalAudioValidation,
    PublishedAsset,
    PublishedEpisode,
    RunState,
)
from audio_engine.audio import AudioTools, assemble_final_audio, open_audio_run
from audio_engine.config import EngineSettings
from audio_engine.leases import FeedLockManager, FeedLockTimeout, LeaseError, LeaseManager
from audio_engine.lifecycle import (
    LifecycleError,
    RunWorkspace,
    load_run_state,
    record_publication_issue,
    record_publication_success,
)
from audio_engine.profile import EpisodeProfile
from audio_engine.safety import ObjectKeyPolicy, SafetyError, resolve_within_roots
from audio_engine.storage import (
    StorageError,
    atomic_write_bytes,
    json_bytes,
    sha256_bytes,
    sha256_file,
)
from audio_engine.validation import load_artifact_file

_FEED_CONTENT_TYPE = "application/rss+xml"
_FEED_CACHE_CONTROL = "no-cache, no-store, must-revalidate"
_ASSET_CACHE_CONTROL = "public, max-age=86400"
_MAX_FEED_BYTES = 2 * 1024 * 1024
_FEED_WRITE_ATTEMPTS = 3
_ITUNES = "http://www.itunes.com/dtds/podcast-1.0.dtd"
_PODCAST = "https://podcastindex.org/namespace/1.0"
_ATOM = "http://www.w3.org/2005/Atom"

ET.register_namespace("atom", _ATOM)
ET.register_namespace("itunes", _ITUNES)
ET.register_namespace("podcast", _PODCAST)


class PublicationError(RuntimeError):
    """A concise publication error that never includes a tokenized location."""


class PreconditionFailed(PublicationError):
    """The object changed since the caller's last read."""


@dataclass(frozen=True)
class StoredObject:
    body: bytes
    etag: str
    content_type: str
    cache_control: str | None
    sha256: str


@dataclass(frozen=True)
class ObjectHead:
    etag: str
    content_type: str
    cache_control: str | None
    bytes: int
    sha256: str


class ObjectStore(Protocol):
    """The narrow object operations required by podcast publication."""

    def get(self, key: str) -> StoredObject | None: ...

    def put(
        self,
        key: str,
        body: bytes | Path,
        *,
        content_type: str,
        cache_control: str | None,
        sha256: str,
        if_match: str | None = None,
        if_none_match: bool = False,
    ) -> str: ...

    def head(self, key: str) -> ObjectHead: ...

    def verify_public(
        self,
        key: str,
        *,
        content_type: str,
        bytes: int,
        sha256: str,
    ) -> None: ...

    def delete(self, key: str) -> None: ...


class MemoryObjectStore:
    """Thread-safe deterministic adapter for development and tests."""

    def __init__(self) -> None:
        self._objects: dict[str, StoredObject] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> StoredObject | None:
        with self._lock:
            return self._objects.get(key)

    def put(
        self,
        key: str,
        body: bytes | Path,
        *,
        content_type: str,
        cache_control: str | None,
        sha256: str,
        if_match: str | None = None,
        if_none_match: bool = False,
    ) -> str:
        payload = body.read_bytes() if isinstance(body, Path) else body
        actual_hash = sha256_bytes(payload)
        if actual_hash != sha256:
            raise PublicationError("object body does not match its declared hash")
        etag = f'"{hashlib.sha256(payload).hexdigest()}"'
        with self._lock:
            existing = self._objects.get(key)
            if if_none_match and existing is not None:
                raise PreconditionFailed("conditional object creation failed")
            if if_match is not None and (existing is None or existing.etag != if_match):
                raise PreconditionFailed("conditional object replacement failed")
            self._objects[key] = StoredObject(
                payload,
                etag,
                content_type,
                cache_control,
                actual_hash,
            )
        return etag

    def head(self, key: str) -> ObjectHead:
        with self._lock:
            stored = self._objects.get(key)
        if stored is None:
            raise PublicationError("object HEAD verification failed")
        return ObjectHead(
            stored.etag,
            stored.content_type,
            stored.cache_control,
            len(stored.body),
            stored.sha256,
        )

    def verify_public(
        self,
        key: str,
        *,
        content_type: str,
        bytes: int,
        sha256: str,
    ) -> None:
        head = self.head(key)
        if (
            _normalize_media_type(head.content_type) != _normalize_media_type(content_type)
            or head.bytes != bytes
            or head.sha256 != sha256
        ):
            raise PublicationError("public object verification failed")

    def delete(self, key: str) -> None:
        with self._lock:
            self._objects.pop(key, None)

    @property
    def objects(self) -> dict[str, StoredObject]:
        """Return a snapshot for deterministic development inspection."""
        with self._lock:
            return dict(self._objects)


@dataclass(frozen=True)
class PublicationContext:
    workspace: RunWorkspace
    manager: LeaseManager
    profile: EpisodeProfile
    state: RunState
    dossier: EvidenceDossier
    plan: EditorialPlan
    transcript: str
    final_audio: FinalAudioValidation


@dataclass(frozen=True)
class PublicationResult:
    status: Literal["published", "already_published", "deferred"]
    episode_key: str
    asset_count: int

    def to_dict(self) -> dict[str, object]:
        return {
            "asset_count": self.asset_count,
            "episode_key": self.episode_key,
            "status": self.status,
        }


@dataclass(frozen=True)
class _Upload:
    kind: Literal["audio", "transcript", "show_notes", "episode_metadata"]
    key: str
    public_url: str
    media_type: str
    body: bytes | Path
    bytes: int
    sha256: str
    cache_control: str = _ASSET_CACHE_CONTROL

    def published_asset(self) -> PublishedAsset:
        return PublishedAsset.model_validate(
            {
                "kind": self.kind,
                "object_key": self.key,
                "public_url": self.public_url,
                "media_type": self.media_type,
                "bytes": self.bytes,
                "sha256": None if self.kind == "episode_metadata" else self.sha256,
            }
        )


def open_publication_run(
    run_directory: Path,
    *,
    settings: EngineSettings,
    repo_root: Path,
    audio_tools: AudioTools | None = None,
) -> PublicationContext:
    """Open a publication-stage run and fully revalidate its final audio and evidence."""
    audio_context = open_audio_run(run_directory, settings=settings, repo_root=repo_root)
    assemble_final_audio(audio_context, tools=audio_tools)
    tts = audio_context.rendering.tts
    state = load_run_state(tts.workspace.state_path)
    if state.current_stage != "publication" or state.final_audio_validation.status != "valid":
        raise PublicationError("publication requires a valid final MP3")
    dossier_reference = state.artifacts.get("evidence_dossier")
    if dossier_reference is None:
        raise PublicationError("publication evidence reference is missing")
    try:
        dossier_path = resolve_within_roots(
            tts.workspace.run_directory / dossier_reference.path,
            [tts.workspace.run_directory],
            must_exist=True,
        )
        dossier, report = load_artifact_file("evidence", dossier_path)
        if (
            sha256_file(dossier_path) != dossier_reference.sha256
            or not report.valid
            or not isinstance(dossier, EvidenceDossier)
        ):
            raise PublicationError("publication evidence no longer matches run state")
    except (OSError, SafetyError, StorageError) as error:
        raise PublicationError("publication evidence is missing or unreadable") from error
    return PublicationContext(
        workspace=tts.workspace,
        manager=tts.manager,
        profile=tts.profile,
        state=state,
        dossier=dossier,
        plan=tts.plan,
        transcript=tts.transcript,
        final_audio=state.final_audio_validation,
    )


def publish_episode(
    run_directory: Path,
    *,
    settings: EngineSettings,
    repo_root: Path,
    store: ObjectStore | None = None,
    clock: Callable[[], datetime] | None = None,
    feed_lock: FeedLockManager | None = None,
    audio_tools: AudioTools | None = None,
) -> PublicationResult:
    """Upload verified assets, then conditionally expose one validated RSS revision."""
    context = open_publication_run(
        run_directory,
        settings=settings,
        repo_root=repo_root,
        audio_tools=audio_tools,
    )
    from audio_engine.r2 import R2ObjectStore

    selected_store = store or R2ObjectStore.from_engine_settings(settings)
    token = settings.podcast_feed_token.get_secret_value()
    policy = ObjectKeyPolicy(token)
    now = _aware_utc((clock or (lambda: datetime.now(UTC)))())
    was_published = context.state.publication.status == "published"
    try:
        episode, uploads, show_notes_payload, metadata_payload = _prepare_episode(
            context,
            settings=settings,
            policy=policy,
            published_at=_previous_published_at(context) or now,
        )
        atomic_write_bytes(context.workspace.run_directory / "show-notes.html", show_notes_payload)
        for upload in uploads:
            _upload_and_verify(selected_store, upload)
    except (PublicationError, SafetyError, StorageError, OSError) as error:
        _record_issue(context, settings, token, "failed", str(error))
        raise PublicationError(
            "episode assets could not be verified; final audio is preserved for publication retry"
        ) from error

    lock = feed_lock or FeedLockManager(settings.runtime_root)
    feed_key = policy.feed_key()
    feed_url = public_object_url(str(settings.podcast_base_url), feed_key)
    try:
        context.manager.refresh(context.state.episode_key, context.state.run_id)
        with lock.acquire(context.profile.identity.feed_id):
            feed_written = write_feed_revision(
                selected_store,
                feed_key=feed_key,
                profile=context.profile,
                episode=episode,
                feed_url=feed_url,
                retention_days=settings.r2_retention_days,
            )
            if not feed_written:
                _record_issue(
                    context,
                    settings,
                    token,
                    "deferred",
                    "Concurrent feed updates did not converge; rerun publish_episode.py.",
                )
                return PublicationResult("deferred", context.state.episode_key, len(uploads))
            _verify_published_feed(selected_store, feed_key, episode.guid)
    except FeedLockTimeout:
        _record_issue(
            context,
            settings,
            token,
            "deferred",
            "Feed publication is busy; rerun publish_episode.py.",
        )
        return PublicationResult("deferred", context.state.episode_key, len(uploads))
    except (LeaseError, PublicationError) as error:
        _record_issue(context, settings, token, "failed", str(error))
        raise PublicationError(
            "feed publication failed; final audio is preserved for publication retry"
        ) from error

    try:
        metadata_path = context.workspace.run_directory / "published-episode.json"
        atomic_write_bytes(metadata_path, metadata_payload)
        show_notes_reference = ArtifactReference(
            artifact_type="show-notes",
            path="show-notes.html",
            sha256=sha256_bytes(show_notes_payload),
        )
        metadata_reference = ArtifactReference(
            artifact_type="published-episode",
            path="published-episode.json",
            sha256=sha256_bytes(metadata_payload),
        )
        record_publication_success(
            context.workspace,
            context.manager,
            context.state.run_id,
            episode=episode,
            show_notes=show_notes_reference,
            published_episode=metadata_reference,
        )
    except (LifecycleError, StorageError) as error:
        raise PublicationError(
            "remote feed was published but local publication state needs a safe rerun"
        ) from error
    status: Literal["published", "already_published"] = (
        "already_published" if was_published else "published"
    )
    return PublicationResult(status, context.state.episode_key, len(uploads))


def public_object_url(base_url: str, key: str) -> str:
    """Join a validated HTTPS origin and normalized object key without ambiguity."""
    parsed = urlsplit(base_url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or key.startswith("/")
        or "\\" in key
        or "//" in key
        or any(part in {"", ".", ".."} for part in key.split("/"))
    ):
        raise SafetyError("public object URL inputs are unsafe")
    origin = base_url.rstrip("/")
    return f"{origin}/{quote(key, safe='/-._~')}"


def write_feed_revision(
    store: ObjectStore,
    *,
    feed_key: str,
    profile: EpisodeProfile,
    episode: PublishedEpisode,
    feed_url: str,
    retention_days: int,
) -> bool:
    """Boundedly re-read, merge, and conditionally replace one feed revision."""
    for _ in range(_FEED_WRITE_ATTEMPTS):
        current = store.get(feed_key)
        merged = merge_rss_feed(
            current.body if current else None,
            profile=profile,
            episode=episode,
            feed_url=feed_url,
            retention_days=retention_days,
        )
        try:
            store.put(
                feed_key,
                merged,
                content_type=_FEED_CONTENT_TYPE,
                cache_control=_FEED_CACHE_CONTROL,
                sha256=sha256_bytes(merged),
                if_match=current.etag if current else None,
                if_none_match=current is None,
            )
        except PreconditionFailed:
            continue
        return True
    return False


def render_show_notes(
    context: PublicationContext,
    *,
    generated_at: datetime,
    transcript_url: str,
) -> bytes:
    """Render escaped, source-grouped notes from validated deterministic artifacts."""
    profile = context.profile
    plan = context.plan
    candidates = {candidate.candidate_id: candidate for candidate in context.dossier.candidates}
    sources = {source.source_id: source for source in context.dossier.sources}
    lines = [
        "<!doctype html>",
        f'<html lang="{html.escape(profile.publishing.language, quote=True)}">',
        '<head><meta charset="utf-8"><title>'
        + html.escape(context.workspace.episode_title)
        + "</title></head>",
        "<body>",
        f"<h1>{html.escape(context.workspace.episode_title)}</h1>",
        "<h2>Episode summary</h2>",
        f"<p>{html.escape(profile.identity.description)}</p>",
        f"<p>{html.escape(plan.opening_approach)}</p>",
        f"<p>{html.escape(plan.closing_takeaway)}</p>",
    ]
    elapsed = 0
    for segment in sorted(plan.segments, key=lambda item: item.order):
        candidate = candidates[segment.candidate_id]
        timestamp = _duration_label(elapsed)
        lines.extend(
            [
                "<section>",
                f'<h2><time datetime="PT{elapsed}S">{timestamp}</time> — '
                f"{html.escape(candidate.title)}</h2>",
                f"<p>{html.escape(candidate.summary)}</p>",
                f"<p><strong>Why it matters:</strong> {html.escape(segment.why_it_matters)}</p>",
                "<h3>Sources</h3>",
                "<ul>",
            ]
        )
        for source_id in candidate.source_ids:
            source = sources[source_id]
            label = f"{source.creator_or_publisher}: {source.title}"
            source_url = _safe_source_url(source.canonical_locator)
            timestamp_text = _source_timestamp(source)
            if source_url:
                entry = (
                    f'<a href="{html.escape(source_url, quote=True)}" rel="noopener noreferrer">'
                    f"{html.escape(label)}</a>"
                )
            else:
                entry = html.escape(label)
            lines.append(f"<li>{entry}{html.escape(timestamp_text)}</li>")
        lines.extend(["</ul>", "</section>"])
        elapsed += segment.desired_duration_seconds
    lines.extend(
        [
            "<h2>Transcript</h2>",
            f'<p><a href="{html.escape(transcript_url, quote=True)}">'
            "Open the plain-text transcript</a>.</p>",
            "<h2>Disclosure</h2>",
            "<p>This episode was generated with AI from the cited source material and "
            "validated production artifacts.</p>",
            f'<p>Episode generation date: <time datetime="{generated_at.date().isoformat()}">'
            f"{generated_at.date().isoformat()}</time>.</p>",
            "</body>",
            "</html>",
            "",
        ]
    )
    return "\n".join(lines).encode("utf-8")


def merge_rss_feed(
    current: bytes | None,
    *,
    profile: EpisodeProfile,
    episode: PublishedEpisode,
    feed_url: str,
    retention_days: int,
) -> bytes:
    """Upsert one GUID into the latest feed, prune expiry-bound items, and validate it."""
    if current is None:
        root = ET.Element("rss", {"version": "2.0"})
        channel = ET.SubElement(root, "channel")
        ET.SubElement(channel, "title").text = profile.publishing.feed_title
        ET.SubElement(channel, "link").text = feed_url
        ET.SubElement(channel, "description").text = profile.identity.description
        ET.SubElement(channel, "language").text = profile.publishing.language
        ET.SubElement(
            channel,
            f"{{{_ATOM}}}link",
            {"href": feed_url, "rel": "self", "type": _FEED_CONTENT_TYPE},
        )
    else:
        root, channel = _parse_rss(current)
        _set_channel_text(channel, "title", profile.publishing.feed_title)
        _set_channel_text(channel, "link", feed_url)
        _set_channel_text(channel, "description", profile.identity.description)
        _set_channel_text(channel, "language", profile.publishing.language)
        atom_link = channel.find(f"{{{_ATOM}}}link")
        if atom_link is None:
            atom_link = ET.SubElement(channel, f"{{{_ATOM}}}link")
        atom_link.attrib.update({"href": feed_url, "rel": "self", "type": _FEED_CONTENT_TYPE})
    _set_channel_text(channel, "lastBuildDate", format_datetime(episode.published_at))
    boundary = episode.episode_date - timedelta(days=retention_days)
    retained: list[ET.Element] = []
    for item in channel.findall("item"):
        channel.remove(item)
        guid = (item.findtext("guid") or "").strip()
        if guid == episode.guid:
            continue
        item_date = _rss_item_date(item)
        if item_date is not None and item_date <= boundary:
            continue
        retained.append(item)
    retained.append(_rss_item(episode))
    retained.sort(key=_rss_sort_instant, reverse=True)
    for item in retained:
        channel.append(item)
    payload = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    validate_rss(payload, expected_guid=episode.guid)
    if len(payload) > _MAX_FEED_BYTES:
        raise PublicationError("merged RSS exceeds the safe size limit")
    return payload


def validate_rss(payload: bytes, *, expected_guid: str | None = None) -> None:
    """Reject malformed or incomplete RSS before a conditional feed write."""
    root, channel = _parse_rss(payload)
    if root.attrib.get("version") != "2.0":
        raise PublicationError("RSS version is not 2.0")
    for field in ("title", "link", "description", "language"):
        if not (channel.findtext(field) or "").strip():
            raise PublicationError("RSS channel metadata is incomplete")
    atom_link = channel.find(f"{{{_ATOM}}}link")
    if (
        atom_link is None
        or atom_link.attrib.get("rel") != "self"
        or atom_link.attrib.get("type") != _FEED_CONTENT_TYPE
        or not _is_https_url(atom_link.attrib.get("href", ""))
        or not _is_https_url(channel.findtext("link") or "")
    ):
        raise PublicationError("RSS channel URLs are incomplete or unsafe")
    guids: list[str] = []
    for item in channel.findall("item"):
        guid = (item.findtext("guid") or "").strip()
        enclosure = item.find("enclosure")
        transcript = item.find(f"{{{_PODCAST}}}transcript")
        guid_element = item.find("guid")
        duration = (item.findtext(f"{{{_ITUNES}}}duration") or "").strip()
        link = (item.findtext("link") or "").strip()
        try:
            enclosure_length = (
                int(enclosure.attrib.get("length", "")) if enclosure is not None else 0
            )
            duration_seconds = int(duration)
            publication_date = parsedate_to_datetime(item.findtext("pubDate") or "")
        except (TypeError, ValueError) as error:
            raise PublicationError("RSS item numeric metadata is invalid") from error
        if publication_date.tzinfo is None or publication_date.utcoffset() is None:
            raise PublicationError("RSS item publication date is invalid")
        if (
            not guid
            or not (item.findtext("title") or "").strip()
            or not (item.findtext("pubDate") or "").strip()
            or not (item.findtext("description") or "").strip()
            or enclosure is None
            or enclosure.attrib.get("type") != "audio/mpeg"
            or enclosure_length < 1
            or duration_seconds < 1
            or transcript is None
            or transcript.attrib.get("type") != "text/plain"
            or guid_element is None
            or guid_element.attrib.get("isPermaLink") != "false"
            or not _is_https_url(enclosure.attrib.get("url", ""))
            or not _is_https_url(transcript.attrib.get("url", ""))
            or not _is_https_url(link)
        ):
            raise PublicationError("RSS item is incomplete or unsafe")
        guids.append(guid)
    if len(guids) != len(set(guids)):
        raise PublicationError("RSS contains duplicate episode GUIDs")
    if expected_guid is not None and guids.count(expected_guid) != 1:
        raise PublicationError("RSS upsert did not produce exactly one episode item")


def _prepare_episode(
    context: PublicationContext,
    *,
    settings: EngineSettings,
    policy: ObjectKeyPolicy,
    published_at: datetime,
) -> tuple[PublishedEpisode, tuple[_Upload, ...], bytes, bytes]:
    state = context.state
    episode_date = state.episode_date
    audio_reference = state.final_audio_validation.artifact
    script_reference = state.artifacts.get("episode_script")
    transcript_reference = state.artifacts.get("transcript")
    if (
        episode_date is None
        or audio_reference is None
        or script_reference is None
        or transcript_reference is None
        or context.final_audio.bytes is None
        or context.final_audio.duration_seconds is None
    ):
        raise PublicationError("publication inputs are incomplete")
    base_url = str(settings.podcast_base_url)
    audio_path = context.workspace.run_directory / audio_reference.path
    transcript_path = context.workspace.run_directory / transcript_reference.path
    if (
        not audio_path.is_file()
        or not transcript_path.is_file()
        or sha256_file(audio_path) != audio_reference.sha256
        or sha256_file(transcript_path) != transcript_reference.sha256
    ):
        raise PublicationError("publication input hashes no longer match their files")
    transcript_key = policy.episode_key(state.profile_id, episode_date, "transcript.txt")
    transcript_url = public_object_url(base_url, transcript_key)
    show_notes = render_show_notes(
        context,
        generated_at=published_at,
        transcript_url=transcript_url,
    )
    notes_hash = sha256_bytes(show_notes)
    notes_reference = ArtifactReference(
        artifact_type="show-notes",
        path="show-notes.html",
        sha256=notes_hash,
    )
    raw_uploads = (
        _Upload(
            "audio",
            policy.episode_key(state.profile_id, episode_date, "episode.mp3"),
            "",
            "audio/mpeg",
            audio_path,
            context.final_audio.bytes,
            audio_reference.sha256,
        ),
        _Upload(
            "transcript",
            transcript_key,
            "",
            "text/plain; charset=utf-8",
            transcript_path,
            transcript_path.stat().st_size,
            transcript_reference.sha256,
        ),
        _Upload(
            "show_notes",
            policy.episode_key(state.profile_id, episode_date, "show-notes.html"),
            "",
            "text/html; charset=utf-8",
            show_notes,
            len(show_notes),
            notes_hash,
        ),
    )
    uploads = tuple(
        _Upload(
            upload.kind,
            upload.key,
            public_object_url(base_url, upload.key),
            upload.media_type,
            upload.body,
            upload.bytes,
            upload.sha256,
        )
        for upload in raw_uploads
    )
    metadata_key = policy.episode_key(state.profile_id, episode_date, "episode.json")
    metadata_url = public_object_url(base_url, metadata_key)
    metadata_asset = PublishedAsset.model_validate(
        {
            "kind": "episode_metadata",
            "object_key": metadata_key,
            "public_url": metadata_url,
            "media_type": "application/json",
            "bytes": 1,
            "sha256": None,
        }
    )
    episode = PublishedEpisode(
        contract_version="1.0",
        prompt_version=None,
        run_id=state.run_id,
        episode_key=state.episode_key,
        profile_id=state.profile_id,
        episode_date=episode_date,
        guid=f"{context.profile.identity.feed_id}:{state.profile_id}:{episode_date.isoformat()}",
        title=context.workspace.episode_title,
        description=context.profile.identity.description,
        published_at=published_at,
        status="published",
        episode_script=script_reference,
        audio=audio_reference,
        transcript=transcript_reference,
        show_notes=notes_reference,
        duration_seconds=max(1, round(context.final_audio.duration_seconds)),
        enclosure_bytes=context.final_audio.bytes,
        enclosure_media_type="audio/mpeg",
        assets=[*(upload.published_asset() for upload in uploads), metadata_asset],
    )
    episode, metadata_payload = _finalize_metadata_size(episode)
    metadata_upload = _Upload(
        "episode_metadata",
        metadata_key,
        metadata_url,
        "application/json",
        metadata_payload,
        len(metadata_payload),
        sha256_bytes(metadata_payload),
    )
    return episode, (*uploads, metadata_upload), show_notes, metadata_payload


def _finalize_metadata_size(episode: PublishedEpisode) -> tuple[PublishedEpisode, bytes]:
    for _ in range(5):
        payload = json_bytes(episode.model_dump(mode="json"))
        actual_size = len(payload)
        metadata = next(asset for asset in episode.assets if asset.kind == "episode_metadata")
        if metadata.bytes == actual_size:
            return episode, payload
        data = episode.model_dump(mode="json")
        assets = cast(list[dict[str, object]], data["assets"])
        for asset in assets:
            if asset.get("kind") == "episode_metadata":
                asset["bytes"] = actual_size
        episode = PublishedEpisode.model_validate(data)
    raise PublicationError("episode metadata size did not stabilize")


def _upload_and_verify(store: ObjectStore, upload: _Upload) -> None:
    store.put(
        upload.key,
        upload.body,
        content_type=upload.media_type,
        cache_control=upload.cache_control,
        sha256=upload.sha256,
    )
    head = store.head(upload.key)
    if (
        _normalize_media_type(head.content_type) != _normalize_media_type(upload.media_type)
        or head.cache_control != upload.cache_control
        or head.bytes != upload.bytes
        or head.sha256 != upload.sha256
    ):
        raise PublicationError("uploaded episode asset failed HEAD verification")
    store.verify_public(
        upload.key,
        content_type=upload.media_type,
        bytes=upload.bytes,
        sha256=upload.sha256,
    )


def _verify_published_feed(store: ObjectStore, feed_key: str, expected_guid: str) -> None:
    current = store.get(feed_key)
    if current is None:
        raise PublicationError("published RSS could not be read back")
    validate_rss(current.body, expected_guid=expected_guid)
    head = store.head(feed_key)
    if (
        _normalize_media_type(head.content_type) != _FEED_CONTENT_TYPE
        or head.cache_control != _FEED_CACHE_CONTROL
        or head.bytes != len(current.body)
        or head.sha256 != current.sha256
    ):
        raise PublicationError("published RSS failed HEAD verification")
    store.verify_public(
        feed_key,
        content_type=_FEED_CONTENT_TYPE,
        bytes=len(current.body),
        sha256=current.sha256,
    )


def _record_issue(
    context: PublicationContext,
    settings: EngineSettings,
    token: str,
    status: Literal["deferred", "failed"],
    message: str,
) -> None:
    try:
        record_publication_issue(
            context.workspace,
            context.manager,
            context.state.run_id,
            status=status,
            message=message,
            sensitive_values=(
                settings.r2_access_key_id.get_secret_value(),
                settings.r2_secret_access_key.get_secret_value(),
                str(settings.r2_endpoint_url),
            ),
            feed_token=token,
        )
    except LifecycleError as error:
        raise PublicationError("publication recovery state could not be recorded") from error


def _previous_published_at(context: PublicationContext) -> datetime | None:
    reference = context.state.artifacts.get("published_episode")
    if context.state.publication.status != "published" or reference is None:
        return None
    try:
        path = resolve_within_roots(
            context.workspace.run_directory / reference.path,
            [context.workspace.run_directory],
            must_exist=True,
        )
        episode, report = load_artifact_file("published-episode", path)
        if (
            sha256_file(path) == reference.sha256
            and report.valid
            and isinstance(episode, PublishedEpisode)
            and episode.episode_key == context.state.episode_key
        ):
            return episode.published_at
    except (OSError, SafetyError, StorageError):
        pass
    return None


def _rss_item(episode: PublishedEpisode) -> ET.Element:
    assets = {asset.kind: asset for asset in episode.assets}
    audio = assets["audio"]
    transcript = assets["transcript"]
    notes = assets["show_notes"]
    item = ET.Element("item")
    ET.SubElement(item, "title").text = episode.title
    ET.SubElement(item, "description").text = episode.description
    ET.SubElement(item, "link").text = str(notes.public_url)
    ET.SubElement(item, "guid", {"isPermaLink": "false"}).text = episode.guid
    ET.SubElement(item, "pubDate").text = format_datetime(episode.published_at)
    ET.SubElement(
        item,
        "enclosure",
        {
            "url": str(audio.public_url),
            "length": str(episode.enclosure_bytes),
            "type": episode.enclosure_media_type,
        },
    )
    ET.SubElement(item, f"{{{_ITUNES}}}duration").text = str(episode.duration_seconds)
    ET.SubElement(
        item,
        f"{{{_PODCAST}}}transcript",
        {"url": str(transcript.public_url), "type": "text/plain"},
    )
    return item


def _parse_rss(payload: bytes) -> tuple[ET.Element, ET.Element]:
    if (
        len(payload) > _MAX_FEED_BYTES
        or b"<!DOCTYPE" in payload.upper()
        or b"<!ENTITY" in payload.upper()
    ):
        raise PublicationError("RSS input is unsafe or oversized")
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as error:
        raise PublicationError("RSS XML is malformed") from error
    channel = root.find("channel") if root.tag == "rss" else None
    if channel is None:
        raise PublicationError("RSS channel is missing")
    return root, channel


def _set_channel_text(channel: ET.Element, tag: str, value: str) -> None:
    element = channel.find(tag)
    if element is None:
        element = ET.SubElement(channel, tag)
    element.text = value


def _rss_item_date(item: ET.Element) -> date | None:
    try:
        return parsedate_to_datetime(item.findtext("pubDate") or "").date()
    except (TypeError, ValueError):
        return None


def _rss_sort_instant(item: ET.Element) -> datetime:
    try:
        value = parsedate_to_datetime(item.findtext("pubDate") or "")
    except (TypeError, ValueError):
        return datetime.min.replace(tzinfo=UTC)
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _safe_source_url(value: str) -> str | None:
    parsed = urlsplit(value)
    if parsed.scheme in {"http", "https"} and parsed.hostname and not parsed.username:
        return value
    return None


def _source_timestamp(source: object) -> str:
    published = getattr(source, "published_at", None)
    updated = getattr(source, "updated_at", None)
    if published is not None:
        return f" (published {published.date().isoformat()})"
    if updated is not None:
        return f" (updated {updated.date().isoformat()})"
    return ""


def _duration_label(seconds: int) -> str:
    hours, remainder = divmod(seconds, 3600)
    minutes, remaining_seconds = divmod(remainder, 60)
    return (
        f"{hours:02d}:{minutes:02d}:{remaining_seconds:02d}"
        if hours
        else f"{minutes:02d}:{remaining_seconds:02d}"
    )


def _is_https_url(value: str) -> bool:
    parsed = urlsplit(value)
    return (
        parsed.scheme == "https"
        and bool(parsed.hostname)
        and not parsed.username
        and not parsed.password
    )


def _normalize_media_type(value: str) -> str:
    return ";".join(part.strip().lower() for part in value.split(";"))


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise PublicationError("publication clock must return a timezone-aware datetime")
    return value.astimezone(UTC)
