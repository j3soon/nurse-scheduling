---
name: screenshot-xlsx
description: Render a real XLSX worksheet or selected range as a deterministic PNG preview with spreadsheet chrome, workbook cell values, fills, fonts, alignment, and borders. Use when Codex needs an embeddable screenshot-like image for documentation, review, or examples and a native Excel or LibreOffice window capture is not required.
---

# Screenshot XLSX

Create a PNG from workbook data with `scripts/render-xlsx.mjs`. Treat the result
as a rendered workbook preview, not a literal capture of Excel or LibreOffice.

## Choose the capture method

- Use the bundled renderer for cell-based schedules, reports, and tables.
- Use a native spreadsheet application when the user needs application chrome,
  charts, macros, images, complex merged cells, or exact conditional formatting.
- Use test or anonymized data unless the user authorizes sensitive workbook data.

## Render a workbook

1. Identify the source XLSX, target PNG, worksheet, and useful range. Keep the
   image focused. Do not expose unrelated rows or columns.
2. Find a module root containing `exceljs` and `sharp`. Prefer an existing
   project dependency directory. Do not modify a lockfile merely to render an
   image without user authorization.
3. Select important cells to verify with repeatable `--expect CELL=VALUE`
   arguments. Include status, score, totals, or a representative result when
   available.
4. Run the script from any directory:

```bash
node /path/to/screenshot-xlsx/scripts/render-xlsx.mjs \
  /path/to/input.xlsx /path/to/output.png \
  --module-root /path/to/project-with-node-modules \
  --sheet Sheet1 \
  --range A1:M16 \
  --expect 'B3=D [D]' \
  --expect 'B14=OPTIMAL'
```

Use `bun` instead of `node` when that is the repository standard. Pass
`--force` only after confirming that replacing the target PNG is intended.

## Validate the image

1. Inspect the PNG with the available image viewer.
2. Confirm asserted values, labels, range boundaries, text legibility, fills,
   and borders.
3. Narrow the range or choose another sheet when the image is too dense.
4. Verify the final documentation or page resolves the image without a 404.
5. Remove only temporary workbooks and outputs created for validation. Never
   delete the user's source workbook.

The renderer reads cached formula results and does not calculate formulas.
Open the workbook in a spreadsheet engine first when cached values are absent.

## Report the method

State that the PNG is rendered from the real XLSX cell model. Do not describe it
as a native Excel or LibreOffice screenshot unless a native application was
actually used.
