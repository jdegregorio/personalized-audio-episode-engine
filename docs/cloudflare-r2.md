# Cloudflare R2 bootstrap

Cloudflare R2 is the MVP's only production publication service. Runtime code will upload podcast objects through the S3-compatible API; resource administration remains an explicit owner action in the Cloudflare dashboard.

The bucket is public at unguessable object URLs. This is suitable only for the public-news MVP. It is not authenticated private storage and must not be reused for personal calendar, email, health, financial, or similarly sensitive content.

## Prerequisites and least privilege

Use an owner-controlled Cloudflare session to enable R2 and complete one-time administration. Accept any billing prerequisite shown by Cloudflare; repository documentation intentionally makes no time-sensitive price or free-tier promise.

The eventual runtime credential needs only **Object Read & Write** access to one dedicated bucket. It must not create buckets, public domains, lifecycle policies, or API tokens. Do not give runtime code a Cloudflare global API key or an administrative R2 token.

## One-time dashboard procedure

1. In **R2 object storage**, create a dedicated bucket with a neutral name. Record the bucket name as `R2_BUCKET_NAME`.
2. From the account and bucket details, record the S3 API endpoint in the form `https://<ACCOUNT_ID>.r2.cloudflarestorage.com` as `R2_ENDPOINT_URL`. Do not derive it from the public URL.
3. In the bucket's public-access settings, enable the Cloudflare-provided `r2.dev` development URL for the fastest proof of concept, or connect a custom HTTPS domain. Record only the origin, with no token or object key, as `PODCAST_BASE_URL`.
4. Treat `r2.dev` as a deliberately accepted proof-of-concept endpoint: Cloudflare documents it as intended for non-production use and subject to rate limiting. A custom domain is recommended for a durable daily schedule and changes configuration, not object layout.
5. Add one lifecycle rule whose prefix is exactly `episodes/` and whose expiration age equals `R2_RETENTION_DAYS` (the initial recommendation is 30 days). Do not apply expiration to `feeds/`. Lifecycle deletion is asynchronous, so the publisher will prune feed entries before objects reach the configured boundary.
6. Create an R2 API token restricted to this bucket with Object Read & Write permission. Capture the Access Key ID as `R2_ACCESS_KEY_ID` and Secret Access Key as `R2_SECRET_ACCESS_KEY` immediately; Cloudflare does not display the secret again.
7. Run the external setup helper described in [`setup.md`](setup.md) to store the values locally and synchronize the `live-smoke` GitHub environment. The helper never receives an administrative credential.

Authoritative references:

- [S3-compatible API](https://developers.cloudflare.com/r2/get-started/s3/)
- [Cloudflare boto3 example](https://developers.cloudflare.com/r2/examples/aws/boto3/)
- [Public buckets and custom domains](https://developers.cloudflare.com/r2/buckets/public-buckets/)
- [R2 API tokens](https://developers.cloudflare.com/r2/api/tokens/)
- [Object lifecycle rules](https://developers.cloudflare.com/r2/buckets/object-lifecycles/)
- [R2 consistency model](https://developers.cloudflare.com/r2/reference/consistency/)

## Secret feed path and object layout

The helper generates or preserves a high-entropy `PODCAST_FEED_TOKEN`. If generating it manually, use at least 32 random bytes and store the result immediately outside the repository. Do not include it in shell history, screenshots, issue text, pull requests, logs, or chat.

The application will use this fixed layout:

```text
feeds/<feed-token>/feed.xml
episodes/<feed-token>/<profile-id>-<YYYY-MM-DD>/episode.mp3
episodes/<feed-token>/<profile-id>-<YYYY-MM-DD>/transcript.txt
episodes/<feed-token>/<profile-id>-<YYYY-MM-DD>/show-notes.html
episodes/<feed-token>/<profile-id>-<YYYY-MM-DD>/episode.json
```

Only `episodes/` is lifecycle-managed. Bucket names and disabled object listing are not access controls; secrecy depends on possession of the complete tokenized URL.

## Configuration and GitHub environment

The local mode-`0600` file is the source of truth. The GitHub `live-smoke` environment is limited to `main` and receives the four secrets and four settings listed in [`setup.md`](setup.md). Ordinary `pull_request` jobs receive none of them. Later live workflows request only the narrow subset they need: Gemini tests receive no R2 credentials, and R2 probes receive no Gemini credential.

## Validation

PR 02's doctor validates configuration shape without network writes. PR 11 adds the first authorized non-sensitive R2 probe. That probe will:

1. Upload a randomly named text object below a dedicated probe prefix.
2. read and HEAD it through the S3 endpoint;
3. fetch it through `PODCAST_BASE_URL` and validate status and media type; and
4. delete the probe object.

The probe must not use the feed token in its object name or output. Production publication remains disabled unless the object probe, public endpoint, asset validation, and conditional feed-write tests pass.

## AntennaPod acceptance

After the first validated publication, subscribe AntennaPod to:

```text
<PODCAST_BASE_URL>/feeds/<PODCAST_FEED_TOKEN>/feed.xml
```

Treat the complete value as a secret. Confirm refresh, download, playback, transcript and show-notes links, correct response media types, and same-day rerun behavior. Optional refresh and auto-download settings are a listener preference, not an engine requirement.

## Rotation and rollback

- Rotate a compromised runtime credential by creating a replacement bucket-scoped token, updating the external local file and GitHub environment, testing the replacement, then revoking the old token.
- Rotate a leaked feed URL by generating a new feed token, republishing under the new prefixes, updating AntennaPod, and then removing or allowing lifecycle cleanup of old episode objects. Never publish both tokens in migration evidence.
- Roll back live service by disabling the schedule, disabling bucket public access, and revoking the runtime token. Existing local audio and offline tests remain available.
- If the lifecycle rule is wrong, disable publication until `R2_RETENTION_DAYS` and the exact `episodes/` prefix agree. Never broaden the rule to `feeds/`.
