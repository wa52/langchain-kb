# HALCON `lines_facet` evidence-boundary eval

This Harbor task uses a synthetic HDevelop example and a short frozen paraphrase of the HALCON 24.11.3.0 operator reference. It is intentionally independent of the configured personal knowledge corpus, chat history, MCP configuration, and index. The Docker task environment has no network access. The Harbor adapter injects only these task fixtures into the production `FastRagService` and calls the project's configured LLM from the host; verifier calls are also made by a host-side subprocess. Do not interpret `network_mode = "none"` as isolating those host-side API calls.

The single pass criterion is semantic grounding: the answer must say `light` means bright lines, identify `Lines` as subpixel-precise XLD contours, describe line and curvilinear structure extraction rather than only straight-line finding, and distinguish what the example shows from what the reference documents. Unsupported parameter claims fail.
