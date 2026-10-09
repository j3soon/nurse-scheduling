# Documentation Guidelines

## Writing

- Write pages under `user-guide/` for people who prepare schedules. Use
  task-based steps, plain language, and only the detail needed to complete the
  task.
- Keep one user-guide page for every frontend app page. Page-title help links
  must resolve to the matching page under the deployed `/docs` path.
- Write developer-guide pages for contributors and operators. Keep content
  minimal, precise, and self-contained.
- Keep screenshots focused on a decision or result. Add concise alt text and
  describe any warning that appears in the image. Add screenshots where a
  beginner would otherwise struggle to follow a step.
- Keep Quick Start on a minimal working schedule. On each app-page guide, put
  an anonymized real-scenario example and matching screenshot after the
  introduction.
- Use `core/tests/testcases/real/large-ward-with-87-people-2025-11.yaml` as the
  committed real-scenario example unless another committed fixture better fits
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
- Keep `docs/PRIVACY.md` as a symlink to the root `PRIVACY.md`.

### Wording and terminology

- Use concise, precise, human language. Every sentence should convey a concrete
  action, definition, or explanation that a first-time reader can understand.
  Rewrite or remove vague statements and redundant caveats.
- Identify who or what acts. Use "the ward" or "the person preparing the
  schedule" for human requirements and decisions, "the app" for GUI behavior,
  and "the optimizer" for generating assignments. Avoid "scheduler" and
  "planner" when readers could interpret them as either a person or software.
- Use established terms consistently. Prefer "shift types" to an undefined
  phrase such as "shift families." Distinguish a nurse's monthly primary shift
  from actual daily assignments. Define new concepts, such as near-hard
  constraints, before using them in explanations.
- Keep introductory terminology short, with one bullet per concept in GUI tab
  order explaining its meaning and purpose. Put ward conventions in a separate
  section and detailed examples beside the steps that use them.
- Be specific about ambiguity. Give a concrete example of what needs
  clarification, such as whether "Day" denotes a monthly primary shift or a
  daily staffing count. Ask about unclear source labels or colors instead of
  assuming their meaning.
- Define compact notation before using it. Name the selectors in a request
  tuple and use explicit group or shift-type names. Avoid shorthand such as
  "Day-to-Evening" when it could mean a daily succession or a rule about
  assignments outside a person's monthly primary shift.
- Explain the need and intended effect behind a group or rule, using the
  supplied rationale. A statement that a later rule uses it is insufficient.
  Distinguish confirmed intent from unused optional concepts. State unused
  advanced options briefly with their purpose and scope.
- Present tools and extraction methods as possible approaches with concrete
  examples. A method that worked for one workbook is not a requirement for
  every ward or user.

### Walkthrough flow

- Write instructions a first-time user can follow without guessing. Use the
  GUI's labels, give actions in click order, and supply the values and expected
  result needed to complete each step. Fix under-explained steps after trying
  them in the GUI.
- Number all sections that belong to the task sequence, including validation.
  Keep that numbering consistent in headings and links.
- Keep wording brief while preserving the information needed to act. Prefer
  concise bullets for summaries and add detail where it resolves a concrete
  question. Avoid repeating the same explanation in several places. When
  simplifying or moving content, preserve its information in the relevant
  section.
- Follow GUI tab order where possible. Keep instructions and rationale beside
  the entries they explain. Group similar rules when one explanation covers
  them, and prefer descriptive bullets over tables for groups and rationale.
  Use tables where readers need to compare structured values.
- Explain the input, output, and tutorial scope early. Distinguish source
  workbooks, extracted inputs, scheduling configuration, optimized assignments,
  and any conversion back to the ward's layout that the tutorial skips.
- Keep paragraphs short and focused. Put case-specific run times or results
  in their own paragraph when they interrupt a general explanation. Use the
  same heading for recurring tasks, such as reusing a configuration next month.
- Make large numbers easy to read. Use thousands separators in explanatory
  prose or clear abbreviations accepted by the app, such as `11b`, `11m`, and
  `-100m`. Avoid fractional abbreviations such as `-.1b`, which can be mistaken
  for `-1b`. Preserve literal syntax in code and downloadable files.
- State outcomes explicitly, for example, "Schedule uploaded," followed by
  only the necessary summary. Readers should immediately know whether an
  action succeeded and what still needs attention.

## Figures

- Make architecture and data-flow figures understandable without surrounding
  prose. Use bold titles and short descriptions inside nodes.
- Give each diagram a numbered caption inside its figure. Label arrows with
  their action or data. Verify owners, allocation, cleanup, and persistence
  ordering against code before updating the diagram.
- Keep stored states separate from derived phases. Distinguish preparing a
  resource adapter from allocating a resource when allocation is lazy.
- Give distinct concepts distinct blocks. Preserve meaningful topology when
  adjusting layout.
- Show alternatives as directly labeled branches. Add a decision node only
  when it represents a real decision.
- Keep Mermaid source readable. Avoid invisible layout machinery unless a
  simple declaration cannot produce a clear result.
- Use text or tables below a figure for detail.

## Reproduce pages and links

- Keep module commands in their READMEs. The developer-guide reproduction pages
  and backend deployment page are symlinks to those files.
- Use absolute links in symlinked READMEs so repository and site views resolve
  them from the same place. State each shell block's working directory.
- Link repository files outside the docs with absolute repository URLs.
  Relative site links must stay inside the built documentation.
- Move page paths, navigation entries, and inbound links together. Add permanent
  redirects for published paths and preserve existing heading IDs.
- Git on Windows can check out symlinks as plain text. Enable symlink support
  or use Linux or WSL when building the documentation.

## Validation

- For walkthroughs that claim a GUI can reproduce a bundled schedule, start
  the frontend with `cd web-frontend && bun run dev`, follow the steps in a
  Playwright browser, and download the resulting YAML from Save and Load.
  Compare its scheduling values with the committed fixture using
  `cd web-frontend && bun scripts/compare-schedule-yaml.mjs ../core/tests/testcases/real/large-ward-with-87-people-2025-11.yaml ../artifacts/exported-schedule.yaml`.
  Keep browser downloads and review captures under the ignored `artifacts/`.
- Do not load JavaScript from `polyfill.io`. Prefer a checked-in asset or the
  established CDN already used by the project.
- Run `zensical serve` from the repository root to preview documentation
  changes with automatic reloads.
- Render Mermaid and MathJax changes in both light and dark themes. Check a
  narrow viewport when formulas or wide tables are involved.
- Use Playwright or browser developer tools to capture and inspect rendered
  figures and formulas.
- Wait for `div.mermaid` before capturing a Mermaid diagram. Zensical puts the
  SVG in a closed shadow root, so an SVG locator cannot detect it.
- Run `zensical build --clean --strict` and `git diff --check` before
  finishing.
- When changing the link checker, run
  `python -m unittest discover -s scripts -p test_check_docs_links.py`.
- Run `python scripts/check_docs_links.py` after the build. It checks pages,
  assets, anchors, README references, and redirect targets without network access.
- After renaming a heading, update inbound anchor links and let the Zensical
  build check for stale anchors.
