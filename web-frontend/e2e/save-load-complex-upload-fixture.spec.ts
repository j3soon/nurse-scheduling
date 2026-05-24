/*
 * This file is part of Nurse Scheduling Project, see <https://github.com/j3soon/nurse-scheduling>.
 *
 * Copyright (C) 2023-2026 Johnson Sun
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU Affero General Public License as
 * published by the Free Software Foundation, either version 3 of the
 * License, or (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU Affero General Public License for more details.
 *
 * You should have received a copy of the GNU Affero General Public License
 * along with this program.  If not, see <https://www.gnu.org/licenses/>.
 */

// This test is mostly AI generated.

import { expect, test } from './test';

test('complex YAML upload restores mixed renamed references across multiple downstream pages', async ({ page }) => {
  /*
   * Steps:
   * 1. Confirm the original save/load preview does not already contain the complex uploaded state.
   * 2. Upload one YAML fixture containing people, groups, shift types, counts, affinities, and requirements.
   * 3. Confirm the save/load preview updates to that fixture.
   * 4. Verify multiple downstream pages render the uploaded mixed references correctly.
   */
  const dialogs: string[] = [];
  page.on('dialog', async dialog => {
    dialogs.push(dialog.message());
    await dialog.accept();
  });

  const complexYaml = `apiVersion: test\ndescription: complex uploaded state\ndates:\n  range:\n    startDate: 2026-05-01\n    endDate: 2026-05-01\n  groups: []\npeople:\n  items:\n    - id: P1\n      description: Primary nurse\n      history: []\n    - id: P2\n      description: Secondary nurse\n      history: []\n  groups:\n    - id: Team Alpha\n      members: [P1]\n      description: Main team\n  history: []\nshiftTypes:\n  items:\n    - id: D\n      description: Day\n    - id: N\n      description: Night\n  groups:\n    - id: Day Group\n      members: [D]\n      description: Day shifts\npreferences:\n  - type: at most one shift per day\n  - type: shift request\n    person: [P1]\n    date: [01]\n    shiftType: [D]\n    weight: 2\n  - type: shift count\n    person: [Team Alpha]\n    countDates: [ALL]\n    countShiftTypes: [D]\n    expression: x >= T\n    target: 1\n    weight: 2\n    description: count rule\n  - type: shift affinity\n    date: [01]\n    people1: [P1]\n    people2: [Team Alpha]\n    shiftTypes: [D]\n    weight: 1\n    description: affinity rule\n  - type: shift type requirement\n    description: coverage rule\n    shiftType: [D]\n    requiredNumPeople: 1\n    qualifiedPeople: [Team Alpha]\n    preferredNumPeople: 1\n    date: [01]\n    weight: -2\nexport:\n  formatting:\n    - type: cell\n      targets: [D]\n      backgroundColor: '#00ff00'\n`;

  await page.goto('/save-and-load');
  await expect(page.locator('pre')).not.toContainText('complex uploaded state');
  await expect(page.locator('pre')).not.toContainText('Team Alpha');

  await page.locator('input[type="file"]').setInputFiles({
    name: 'complex.yaml',
    mimeType: 'application/x-yaml',
    buffer: Buffer.from(complexYaml, 'utf8'),
  });

  await expect.poll(() => dialogs.length).toBe(2);
  await expect(page.locator('pre')).toContainText('complex uploaded state');
  await expect(page.locator('pre')).toContainText('Team Alpha');
  await expect(page.locator('pre')).toContainText('Day Group');

  await page.goto('/people');
  await expect(page.getByText('1. P1', { exact: true })).toBeVisible();
  await expect(page.getByTitle('Team Alpha', { exact: true })).toBeVisible();

  await page.goto('/shift-types');
  await expect(page.getByText('1. D', { exact: true })).toBeVisible();
  await expect(page.getByTitle('Day Group', { exact: true })).toBeVisible();

  await page.goto('/shift-counts');
  await expect(page.getByText('People: Team Alpha')).toBeVisible();
  await expect(page.getByText('Count Dates: ALL')).toBeVisible();
  await expect(page.getByText('Count Shift Types: D')).toBeVisible();

  await page.goto('/shift-affinities');
  await expect(page.getByText('People 1: P1')).toBeVisible();
  await expect(page.getByText('People 2: Team Alpha')).toBeVisible();
  await expect(page.getByText('Shift Types: D')).toBeVisible();

  await page.goto('/shift-type-requirements');
  await expect(page.getByText('coverage rule')).toBeVisible();
  await expect(page.getByText('Qualified: Team Alpha')).toBeVisible();
});
