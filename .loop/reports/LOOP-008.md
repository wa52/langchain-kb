# Loop 008 — Scoped Local Filesystem Capability

## Outcome

Completed. The Agent can classify local file/folder operations as filesystem
actions, inspect authorized folders without returning document contents, compare
duplicate files by SHA-256, and import explicitly requested paths through the
existing knowledge ingestion pipeline. Imports require Agent approval and
invalidate retrieval caches after new chunks are written.

The project MCP configuration now grants the exact HALCON examples directory
shown by the user, in addition to roots that were already configured. No broader
root was added. That per-machine `mcp.json` is ignored by Git and is not part of
the commit.

## Safeguards

- Path validation only accepts existing paths below enabled filesystem-server
  roots configured in `mcp.json`.
- Traversed symlinks are resolved and entries escaping the selected root are
  excluded.
- Inspection is limited to supported document types and at most 10,000 files;
  returned names are capped at 500, duplicate results at 200.
- File content is streamed into SHA-256 and never returned in tool output.
- Import uses `run_add_path`, deduplicates against every tracked source hash,
  and only reports newly indexed chunk counts.
- The write tool's Agent execution path is configured for human approval.
- The existing Capability API and UI display metadata, not root paths or file
  contents.

## Verification

- Red-first filesystem/tool and cross-source dedup tests demonstrated the
  missing behavior before implementation.
- Focused filesystem, dedup, routing, selection, and capability API regression:
  43 passed.
- CLI and diagnostics environment-isolation tests: 150 passed.
- Full project suite in `kb_env` on Python 3.13: 773 passed, 1 skipped.
- Capability roots were resolved from config without enumerating their
  contents. No real user directory was opened, hashed, or indexed.
- No Web source change was needed: the existing Capabilities page renders the
  `/api/v1/capabilities` catalog dynamically. Endpoint coverage verifies both
  tools and their read/write risk metadata.

## Notes

The global Python has MCP SDK 2.2, which cannot collect the project's MCP v1
stdio module; the repository's `kb_env` is the supported full-test environment.
The CLI unit tests now mock port/lifecycle state rather than depending on live
ports. They do not stop the running services.
