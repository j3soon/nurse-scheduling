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
// This code is mostly AI generated.

'use client';

import * as Sentry from '@sentry/nextjs';
import { useCallback, useEffect, useMemo, useRef } from 'react';
import { useI18n } from '@/i18n/I18nProvider';
import { getFeedbackOptions } from '@/utils/feedbackOptions';

type FeedbackForm = Awaited<ReturnType<NonNullable<ReturnType<typeof Sentry.getFeedback>>['createForm']>>;

export function useFeedbackForm() {
  const { t } = useI18n();
  const options = useMemo(() => getFeedbackOptions(t), [t]);
  const latestOptions = useRef(options);
  useEffect(() => { latestOptions.current = options; }, [options]);

  // Keep the binding and open draft across streaming renders and locale changes.
  // A new form uses the language selected when the user opens it.
  return useCallback((element: HTMLButtonElement | null) => {
    const feedback = Sentry.getFeedback();
    if (!element || !feedback) return;
    let form: FeedbackForm | null = null;
    let opening = false;
    let disposed = false;
    const removeForm = () => {
      form?.removeFromDom();
      form = null;
    };
    const open = async () => {
      if (opening) return;
      opening = true;
      try {
        if (!form) {
          const created = await feedback.createForm({
            ...latestOptions.current,
            onFormClose: removeForm,
            onFormSubmitted: removeForm,
          });
          if (disposed) {
            created.removeFromDom();
            return;
          }
          form = created;
          form.appendToDom();
        }
        form.open();
      } catch (error) {
        Sentry.captureException(error);
      } finally {
        opening = false;
      }
    };
    element.addEventListener('click', open);
    return () => {
      disposed = true;
      element.removeEventListener('click', open);
      removeForm();
    };
  }, []);
}
