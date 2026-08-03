# Optional collection capabilities

No separate collector is required for a public-web episode. The production skill uses Codex native research and web search when no suitable specialized capability is already available and the profile permits fallback.

Optional capabilities can improve recall or reach sources that native public-web research cannot access:

| Capability kind | Useful when | Setup boundary |
| --- | --- | --- |
| Research or deep-research skill | Broad multi-source discovery or specialized literature review | Install at user scope through its trusted publisher or Codex skill manager, then confirm it is visible before a production run. |
| Browser or web-search tool | A source requires interactive navigation or rendered pages | Configure the managed tool outside the run and verify it without exposing credentials. |
| Connector or MCP server | The profile explicitly needs an authenticated or non-web resource | Configure least-privilege authentication outside this repository and list the capability as required in the profile. |
| Independently maintained topic collector | A stable source benefits from source-specific normalization | Keep its client and credentials outside the engine; it must output the same evidence-dossier contract. |

These are suggestions, not dependencies. The engine never installs a capability, embeds a source-specific client, or relaxes the evidence contract for one method. Review a capability's publisher, permissions, network access, data handling, and update policy before enabling it.

## Record an available capability

After Codex inspects the current environment and judges a capability suitable, record only its identifier and an observable version:

```bash
uv run python scripts/select_collection_method.py \
  --run <run-directory> \
  --capability <name>=<version> \
  --preferred-capability <name>
```

Omit `=<version>` when the capability exposes none. If an optional capability fails, rerun selection with `--failed-capability <name>` and redeclare every surviving suitable `--capability`. Failed names persist in run state and across compatible cross-invocation resume, so they cannot loop back into selection; the command uses another declared suitable capability or allowed native fallback. A missing profile-required capability fails before editorial work with configuration guidance and is not replaced by a weaker mock.

Do not place capability credentials, private resource locators, or retrieved source dumps in the repository, command line, validation evidence, or pull-request comments.
