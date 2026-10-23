# Loop 016 — Web Visual Hierarchy Pass

## Design decision

The audience is an engineer asking questions of project knowledge and managing
its sources. The main screen should make the next action obvious, while status
and metrics remain available without competing with content. The palette uses
graphite/steel surfaces, mineral teal for the active path, and semantic
green/amber/red for status. Display uses Bahnschrift with a Chinese UI fallback;
body and path data keep separate UI/monospace roles. The source metric strip is
the distinctive element: it reads like a compact technical register instead
of four competing dashboard cards.

As external design references, [Linear's UI redesign](https://linear.app/now/how-we-redesigned-the-linear-ui)
emphasizes a quieter sidebar, aligned headers, and navigation hierarchy;
[Notion's wiki guidance](https://www.notion.com/help/guides/how-to-build-a-wiki-for-your-product-team)
keeps source content accessible from its workspace navigation. Only those
principles were adapted; no product screen was copied.

## Delivered

- Rebalanced the shared header/sidebar, restrained the palette, and fixed
  missing token aliases used by existing controls.
- Made the Knowledge page's add-source action primary and removed its duplicate
  standalone card; grouped the four metrics into responsive pairs with Chinese
  labels. Kept the full file paths and accessible icon actions.
- Changed the Chat empty state from a centered promotional block to a
  left-aligned starting point. No chat/SSE execution code changed.
- Fixed a hidden hint pseudo-element that caused desktop horizontal scrolling
  and improved primary-button contrast in dark mode.

## Verification

- `npm run typecheck` and `npm run build`: passed.
- Isolated full Python regression: 814 passed, 1 skipped, 3 warnings.
- Real running Web app with synthetic sources: reviewed 1280px desktop, 768px
  intermediate, and 390px mobile views. The first pass exposed a cramped graph
  metric at 768px and a tooltip-induced horizontal scrollbar; both were fixed
  and rechecked. Browser measurements showed equal client/scroll widths on the
  final Knowledge and mobile Chat views.
- Mobile add-source drawer opened and closed; long nested source paths, icon
  actions, empty state, and composer stayed reachable. The UI uses the existing
  1.5-second Chinese hint CSS and retained accessible names. No actual index,
  deletion, or model call was issued. The isolated service was stopped after QA.

## Visual self-review (1–5)

Overall coordination 4; hierarchy 4; typography 4; components 4; space 4;
interaction 4; product completion 4 within this scoped pass. Other product
pages, the light OS theme, and error/running states were not visually
re-reviewed; their quality is not inferred from these scores.
