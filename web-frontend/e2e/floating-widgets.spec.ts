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

type Rect = {
  top: number;
  right: number;
  bottom: number;
  left: number;
};

function rectanglesOverlap(a: Rect, b: Rect): boolean {
  return a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top;
}

test('build selector and feedback button do not overlap', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto('/');
  await expect(page.getByRole('button', { name: /Build:/ })).toBeVisible();

  const rects = await page.evaluate(() => {
    const toRect = (element: Element) => {
      const rect = element.getBoundingClientRect();
      return {
        top: rect.top,
        right: rect.right,
        bottom: rect.bottom,
        left: rect.left,
      };
    };

    const buildButton = [...document.querySelectorAll('button')]
      .find((button) => button.textContent?.includes('Build:'));

    const sentryHost = document.getElementById('sentry-feedback');
    let feedbackButton = sentryHost?.shadowRoot?.querySelector('.widget__actor');

    if (!feedbackButton) {
      feedbackButton = document.createElement('button');
      feedbackButton.textContent = 'Report a Bug';
      feedbackButton.setAttribute('aria-label', 'Report a Bug');
      feedbackButton.setAttribute('data-testid', 'mock-sentry-feedback-button');
      feedbackButton.setAttribute(
        'style',
        [
          'position: fixed',
          'right: 16px',
          'bottom: 16px',
          'width: 137.36px',
          'height: 49.95px',
          'z-index: 100000',
        ].join(';'),
      );
      document.body.appendChild(feedbackButton);
    }

    return {
      buildButton: buildButton ? toRect(buildButton) : null,
      feedbackButton: feedbackButton ? toRect(feedbackButton) : null,
    };
  });

  expect(rects.buildButton).not.toBeNull();
  expect(rects.feedbackButton).not.toBeNull();

  const buildButton = rects.buildButton as Rect;
  const feedbackButton = rects.feedbackButton as Rect;

  expect(rectanglesOverlap(buildButton, feedbackButton)).toBe(false);
  expect(feedbackButton.top - buildButton.bottom).toBeGreaterThanOrEqual(14);
});
