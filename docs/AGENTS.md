# Documentation Guidelines

## Writing

- Write for developers. Keep content minimal, precise, and self-contained.
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

- Run `zensical serve` from the repository root to preview documentation
  changes with automatic reloads.
- Render Mermaid and MathJax changes in both light and dark themes. Check a
  narrow viewport when formulas or wide tables are involved.
- Use Playwright or browser developer tools to capture and inspect rendered
  figures and formulas.
- Run `zensical build --clean --strict` and `git diff --check` before
  finishing.
- Verify internal links and referenced assets resolve without 404 responses.
