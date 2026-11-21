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

import yaml from 'js-yaml';
import { expect, test } from './test';
import { disableModalDialogs, seedScheduleSpecState } from './helpers';

test('download after editing YAML reflects the saved edited state', async ({ page }) => {
  /*
   * Steps:
   * 1. Confirm the original YAML contains the seeded group name.
   * 2. Edit and save the YAML with a renamed group.
   * 3. Download the YAML through the real control.
   * 4. Confirm the downloaded content reflects the edited state.
   */
  await disableModalDialogs(page);
  await seedScheduleSpecState(page, {
    apiVersion: 'test',
    description: 'edit download seed',
    dates: { range: { startDate: '2026-05-01', endDate: '2026-05-01' }, groups: [] },
    people: {
      items: [{ id: 'P1', description: 'Primary nurse', history: [] }],
      groups: [{ id: 'Team Alpha', members: ['P1'], description: 'Original team' }],
      history: [],
    },
    shiftTypes: { items: [{ id: 'D', description: 'Day' }], groups: [] },
    preferences: [{ type: 'at most one shift per day' }],
    export: { formatting: [] },
  });

  await page.goto('/save-and-load');
  await expect(page.locator('pre')).toContainText('Team Alpha');
  await page.getByRole('button', { name: 'Edit YAML' }).click();
  const textarea = page.locator('textarea');
  const originalYaml = await textarea.inputValue();
  await textarea.fill(originalYaml.replace('Team Alpha', 'Team Omega'));
  await page.getByRole('button', { name: 'Save', exact: true }).click();
  await expect(page.locator('pre')).toContainText('Team Omega');

  const downloadPromise = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Download' }).click();
  const download = await downloadPromise;
  const content = await download.createReadStream();
  let yamlText = '';
  if (content) {
    for await (const chunk of content) {
      yamlText += chunk.toString();
    }
  }
  expect(yamlText).toContain('Team Omega');
  expect(yamlText).not.toContain('Team Alpha');
});

test('editing the Schedule Spec description updates YAML and creates one Undo step', async ({ page }) => {
  await seedScheduleSpecState(page, {
    apiVersion: 'test',
    description: 'Original description',
    dates: { range: {}, groups: [] },
    people: { items: [], groups: [], history: [] },
    shiftTypes: { items: [], groups: [] },
    preferences: [{ type: 'at most one shift per day', description: 'Keep this rule note' }],
    export: { formatting: [] },
  });

  await page.goto('/save-and-load');
  const description = page.getByLabel('Schedule Spec description (optional)');
  const preview = page.locator('pre');
  await expect(description).toHaveValue('Original description');
  const revised = 'June roster\nIncludes the holiday weekend.';
  await description.fill(revised);
  await expect(preview).toContainText('Original description');
  await page.getByRole('button', { name: 'Save description' }).click();
  await expect(preview).toContainText('June roster');
  expect(yaml.load(await preview.innerText())).toMatchObject({
    description: revised,
    preferences: [{ type: 'at most one shift per day', description: 'Keep this rule note' }],
  });

  await page.keyboard.press('Control+z');
  await expect(description).toHaveValue('Original description');
  await page.keyboard.press('Control+y');
  await expect(description).toHaveValue(revised);
  await page.reload();
  await expect(description).toHaveValue(revised);
});

test('carries a pending description into the YAML editor and back on cancel', async ({ page }) => {
  await seedScheduleSpecState(page, {
    apiVersion: 'test',
    description: 'Original description',
    dates: { range: {}, groups: [] },
    people: { items: [], groups: [], history: [] },
    shiftTypes: { items: [], groups: [] },
    preferences: [],
  });

  await page.goto('/save-and-load');
  const description = page.getByLabel('Schedule Spec description (optional)');
  await expect(description).toHaveValue('Original description');
  await description.fill('Pending description');
  await page.getByRole('button', { name: 'Edit YAML' }).click();
  const editor = page.getByPlaceholder('Enter Schedule Spec YAML...');
  expect(yaml.load(await editor.inputValue())).toMatchObject({ description: 'Pending description' });
  await page.getByRole('button', { name: 'Cancel', exact: true }).click();
  await expect(description).toHaveValue('Pending description');

  await page.getByRole('button', { name: 'Edit YAML' }).click();
  await editor.fill((await editor.inputValue()) + '\n# Checked the YAML\n');
  await page.getByRole('button', { name: 'Save', exact: true }).click();
  await expect(page.locator('pre')).toContainText('Pending description');
  await expect(page.getByRole('button', { name: 'Save description' })).toHaveCount(0);
});

test('confirms replacement when an upload would discard the pending description', async ({ page }) => {
  await seedScheduleSpecState(page, {
    apiVersion: 'test',
    description: 'Original description',
    dates: { range: {}, groups: [] },
    people: { items: [], groups: [], history: [] },
    shiftTypes: { items: [], groups: [] },
    preferences: [],
  });

  await page.goto('/save-and-load');
  const description = page.getByLabel('Schedule Spec description (optional)');
  await expect(description).toHaveValue('Original description');
  const preview = page.locator('pre');
  const matchingYaml = (await preview.innerText()).replace('Original description', 'Uploaded description');
  await description.fill('Pending description');

  for (const accept of [false, true]) {
    const prompt = page.waitForEvent('dialog', { timeout: 5000 });
    const upload = page.locator('input[type="file"]').setInputFiles({
      name: 'replacement.yaml',
      mimeType: 'application/x-yaml',
      buffer: Buffer.from(matchingYaml),
    });
    const dialog = await prompt;
    expect(dialog.message()).toContain('discard the unsaved description');
    if (accept) await dialog.accept();
    else await dialog.dismiss();
    await upload;
    await expect(description).toHaveValue(accept ? 'Uploaded description' : 'Pending description');
  }
});
