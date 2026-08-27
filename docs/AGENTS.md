# Documentation Guidelines

## Writing

- Write pages under `user-guide/` for schedule planners. Use task-based steps,
  plain language, and only the detail needed to complete the task.
- Keep one user-guide page for every frontend app page. Page-title help links
  must resolve to the matching page under the deployed `/docs` path.
- Write developer-guide pages for contributors and operators. Keep content
  minimal, precise, and self-contained.
- Keep screenshots focused on a decision or result. Add concise alt text and
  describe any warning that appears in the image.
- Keep Quick Start on a minimal working schedule. On each app-page guide, put
  an anonymized real-scenario example and matching screenshot after the
  introduction.
- Use `core/tests/testcases/real/large-ward-with-87-people-2025-11.yaml` as the
  canonical real-scenario example unless another committed fixture better fits
  the page.
- Keep Quick Start screenshots separate from app-page screenshots so a
  deep-dive update cannot change the minimal walkthrough.
- State whether a setting is required or optional in prose, not in a section
  title. If the real scenario leaves a page unused, show that empty or default
  state instead of inventing a rule.
- Give Dates, People, and Shift Types the same required-first flow. Explain
  that groups are optional reusable selectors that can be added when later
  rules need them.
- Distinguish a pre-run optimization configuration from a completed solve. Do
  not imply that a solver ran when only backend readiness or UI state was
  prepared for a screenshot.
- Introduce technical concepts in this order: schema or example, description,
  then runtime or optimization behavior.
- Define notation once and use it consistently. Distinguish sets, selected
  subsets, parameters, and decision variables.
- Describe mathematically accurate semantics without exposing unnecessary
  solver linearization details.
- Keep tightly coupled schema and behavior on one page unless each topic has a
  clear independent purpose.
- Keep `docs/PRIVACY.md` as a symlink to the canonical root `PRIVACY.md`.

## Figures

- Make architecture and data-flow figures understandable without surrounding
  prose. Use bold titles and short descriptions inside nodes.
- Give distinct concepts distinct blocks. Preserve meaningful topology when
  adjusting layout.
- Show alternatives as directly labeled branches. Add a decision node only
  when it represents a real decision.
- Keep Mermaid source readable. Avoid invisible layout machinery unless a
  simple declaration cannot produce a clear result.
- Use text or tables below a figure for detail.

## Validation

- Do not load JavaScript from `polyfill.io`. Prefer a checked-in asset or the
  established CDN already used by the project.
- Run `zensical serve` from the repository root to preview documentation
  changes with automatic reloads.
- Render Mermaid and MathJax changes in both light and dark themes. Check a
  narrow viewport when formulas or wide tables are involved.
- Use Playwright or browser developer tools to capture and inspect rendered
  figures and formulas.
- Run `zensical build --clean --strict` and `git diff --check` before
  finishing.
- Verify internal links and referenced assets resolve without 404 responses.
- After renaming a heading, update inbound anchor links and let the Zensical
  build check for stale anchors.
