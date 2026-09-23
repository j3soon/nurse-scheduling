---
name: html-commit-review
description: Build a concise, self-contained HTML review page for one or more git commits under the gitignored repository-root artifacts/ directory, then host it on a loopback port and hand over the URL. The page has a TL;DR per commit, illustrated figures (architecture, sequence, before/after, state machine, trust boundaries), a file-by-file change table, and validation evidence. Use when asked to produce a visual or HTML review of commits for a reviewer to browse, or to host a review artifact. Do not use for code review, commit messages, or artifacts that are not about commits.
---

# HTML Commit Review

Goal: hand the reviewer one file they can skim in minutes and a URL that
opens immediately. Maximize cognitive offload, so the page answers "what
changed, why, and is it safe" without a terminal.

## Gather commit facts

Default target: the last two commits. Use a user-supplied range or hash
instead when given.

1. `git log --oneline -N` and `git log -N --format=fuller` for messages,
   authors, dates, and attribution lines.
2. `git show --stat <hash>` per commit for the file list and line deltas.
3. Read diffs with narrow path filters, module by module
   (`git show <hash> -- core/ web-frontend/ docker/ docs/`). Read large new
   files in chunks with `| head -200` and `sed -n '200,470p'`.
4. Extract test coverage cheaply:
   `git show <hash> -- <test paths> | grep -E '^\+(def |class |  it\()'`.
5. Never dump whole repositories, whole files, or full status output. Keep
   every query scoped to the paths and commits in question.

## Write the page

Write one self-contained `artifacts/<short-slug>.html`. No external CSS,
fonts, JS, or images. Inline CSS and inline SVG only, so the file works
offline and can be sent as a single attachment.

Structure, in order:

1. Sticky nav: Overview, Figures, File-by-file per commit, Evidence.
2. Commit header: short hash, type tag (fix/feat), author and date,
   attribution line.
3. One TL;DR card per commit: problem or goal, three to four key changes,
   file and line stats.
4. Overview: what changes for the user, one paragraph of mental model tying
   the commits together, and design decisions worth a glance.
5. Figures, each with a one-line "how to read this" caption. Pick only what
   fits the change.
   - Architecture (SVG boxes and arrows for the new data path).
   - Sequence diagram (SVG lanes and numbered steps for the new flow).
   - Before/after (side-by-side panels for behavior fixes).
   - State machine (when a new lifecycle exists).
   - Trust or data boundaries (when credentials or untrusted data move).
   - Insertions-by-file bar chart (plain CSS divs, no SVG needed).
6. File-by-file table per commit, grouped by module with header rows.
   Columns: file (monospace), delta lines (+ green, - red), and what
   changed in one to three bullets focused on behavior and invariants.
7. Validation evidence copied from the commit messages.
8. Footer: the exact git commands used to build the page.

Keep color semantics consistent: blue for browser/user, emerald for success
and optimizer status, violet for asynchronous status, red for failure and
pre-fix behavior. Give every SVG a `viewBox` and an `aria-label`. Keep prose
scannable: bullets, bold keywords, short sentences.

## Validate

Run `python3 skills/html-commit-review/scripts/check_html.py <file>` and fix
every unclosed or mismatched tag before serving.

## Host and report

1. Pick a free port by probing candidate loopback ports (8123 through 8125)
   with `(echo > /dev/tcp/127.0.0.1/PORT) 2>/dev/null`.
2. Serve the artifacts directory:
   `cd artifacts && nohup python3 -m http.server PORT --bind 127.0.0.1 > /tmp/review-site.log 2>&1 &`
3. Verify with
   `curl -s -o /dev/null -w "%{http_code} %{size_download}" http://127.0.0.1:PORT/<file>.html`
   and expect 200 with a sane byte count.
4. Report the full URL plus the stop command (`pkill -f "http.server PORT"`).
   Never leave a server running without telling the user its port and how to
   stop it.

## Answer follow-up questions

Reviewers often ask "was X necessary?" or "did Y work before the change?".
Answer from the parent commit, not the diff. Get the parent hash with
`git log -1 --format=%P <hash>`, then confirm whether a symbol or behavior
existed before with `git show <parent>:<path> | grep -n <symbol>`.

## Boundaries

- `artifacts/` is gitignored and disposable. Never stage or commit the page,
  and never cite it in a commit message.
- Keep the server bound to loopback. Do not expose it on other interfaces.
- If the review reveals a real defect, report it instead of silently
  adjusting the page to hide it.
