"""Verify R2 S3 and public access with one disposable non-sensitive object."""

from __future__ import annotations

import argparse
import json
import sys
import uuid

from pydantic import ValidationError

from audio_engine.publication import PreconditionFailed, PublicationError
from audio_engine.r2 import R2ConnectionSettings, R2ObjectStore
from audio_engine.storage import sha256_bytes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    key = f"probes/r2-smoke-{uuid.uuid4().hex}.txt"
    body = b"personalized audio engine R2 smoke\n"
    media_type = "text/plain; charset=utf-8"
    try:
        settings = R2ConnectionSettings()  # pyright: ignore[reportCallIssue]
        store = R2ObjectStore(settings)
        digest = sha256_bytes(body)
        try:
            initial_etag = store.put(
                key,
                body,
                content_type=media_type,
                cache_control="no-store",
                sha256=digest,
                if_none_match=True,
            )
            fetched = store.get(key)
            head = store.head(key)
            if (
                fetched is None
                or fetched.body != body
                or fetched.sha256 != digest
                or head.bytes != len(body)
                or head.sha256 != digest
            ):
                raise PublicationError("R2 probe S3 verification failed")
            store.verify_public(
                key,
                content_type=media_type,
                bytes=len(body),
                sha256=digest,
            )
            updated_body = body + b"conditional write verified\n"
            updated_digest = sha256_bytes(updated_body)
            store.put(
                key,
                updated_body,
                content_type=media_type,
                cache_control="no-store",
                sha256=updated_digest,
                if_match=initial_etag,
            )
            try:
                store.put(
                    key,
                    body,
                    content_type=media_type,
                    cache_control="no-store",
                    sha256=digest,
                    if_match=initial_etag,
                )
            except PreconditionFailed:
                pass
            else:
                raise PublicationError("R2 probe accepted a stale conditional write")
            updated = store.get(key)
            if updated is None or updated.body != updated_body:
                raise PublicationError("R2 probe lost a conditional object revision")
            store.verify_public(
                key,
                content_type=media_type,
                bytes=len(updated_body),
                sha256=updated_digest,
            )
        finally:
            store.delete(key)
    except ValidationError:
        print('{"code":"invalid_settings","result":"failed"}', file=sys.stderr)
        return 1
    except PublicationError as error:
        print(
            json.dumps(
                {"code": "r2_probe_failed", "message": str(error), "result": "failed"},
                separators=(",", ":"),
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1
    print(
        json.dumps(
            {
                "cleanup": "completed",
                "conditional_write": "passed",
                "media_type": media_type,
                "public_fetch": "passed",
                "result": "passed",
                "s3_get": "passed",
                "s3_head": "passed",
            },
            separators=(",", ":"),
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised by the live workflow
    raise SystemExit(main())
