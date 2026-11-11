/*
 * This file is part of Nurse Scheduling Project, see <https://github.com/j3soon/nurse-scheduling>.
 *
 * Copyright (C) 2023-2026 Johnson Sun
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU Affero General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
 * GNU Affero General Public License for more details.
 *
 * You should have received a copy of the GNU Affero General Public License
 * along with this program. If not, see <https://www.gnu.org/licenses/>.
 */

// This code is mostly AI generated.

'use client';

import * as Sentry from '@sentry/nextjs';
import { usePathname } from 'next/navigation';
import { useEffect, useRef } from 'react';
import { useI18n } from '@/i18n/I18nProvider';
import type { Locale } from '@/i18n/messages';
import { getFeedbackOptions } from '@/utils/feedbackOptions';

type FeedbackActor = ReturnType<NonNullable<ReturnType<typeof Sentry.getFeedback>>['createWidget']>;

// On a phone, the AI chat composer fills the bottom of the screen, where the
// floating Feedback button would cover Send. That page offers feedback in its
// chat details panel instead.
export default function FeedbackWidget() {
  const pathname = usePathname();
  const { locale, t } = useI18n();
  const actorsRef = useRef(new Map<Locale, FeedbackActor>());
  const actorRef = useRef<FeedbackActor | null>(null);

  useEffect(() => {
    const feedback = Sentry.getFeedback();
    if (!feedback) return;
    const phone = window.matchMedia('(max-width: 639px)');
    const update = () => {
      if (pathname === '/experimental-ai' && phone.matches) {
        actorRef.current?.removeFromDom();
      } else {
        const actor = actorsRef.current.get(locale);
        if (actorRef.current !== actor) actorRef.current?.removeFromDom();
        if (actor) {
          actor.appendToDom();
          actorRef.current = actor;
        } else {
          actorRef.current = feedback.createWidget(getFeedbackOptions(t));
          actorsRef.current.set(locale, actorRef.current);
        }
      }
    };
    update();
    phone.addEventListener('change', update);
    return () => phone.removeEventListener('change', update);
  }, [pathname, locale, t]);

  useEffect(() => {
    const actors = actorsRef.current;
    return () => {
      actors.forEach(actor => actor.removeFromDom());
      actors.clear();
    };
  }, []);

  return null;
}
