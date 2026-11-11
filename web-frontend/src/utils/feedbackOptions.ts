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

import type { getFeedback } from '@sentry/nextjs';
import type { Translator } from '@/i18n/messages';

type FeedbackOptions = NonNullable<Parameters<NonNullable<ReturnType<typeof getFeedback>>['createWidget']>[0]>;

export function getFeedbackOptions(t: Translator): FeedbackOptions {
  return {
    triggerLabel: t('Feedback'),
    triggerAriaLabel: t('Send feedback'),
    formTitle: t('Send Feedback'),
    messageLabel: t('Feedback'),
    messagePlaceholder: t('Tell us what worked, what did not, or what could be improved.'),
    submitButtonLabel: t('Send Feedback'),
    cancelButtonLabel: t('Cancel'),
    confirmButtonLabel: t('Confirm'),
    nameLabel: t('Name'),
    namePlaceholder: t('Your Name'),
    emailLabel: t('Email'),
    isRequiredLabel: t('(required)'),
    addScreenshotButtonLabel: t('Add a screenshot'),
    removeScreenshotButtonLabel: t('Remove screenshot'),
    highlightToolText: t('Highlight'),
    hideToolText: t('Hide'),
    removeHighlightText: t('Remove'),
    successMessageText: t('Thank you for your report!'),
    errorEmptyMessageText: t('Unable to submit feedback with empty message'),
    errorNoClientText: t('No client setup, cannot send feedback.'),
    errorTimeoutText: t('Unable to determine if Feedback was correctly sent.'),
    errorForbiddenText: t('Unable to send feedback. This could be because this domain is not in your list of allowed domains.'),
    errorGenericText: t('Unable to send feedback. This could be because of network issues, or because you are using an ad-blocker.'),
  };
}
