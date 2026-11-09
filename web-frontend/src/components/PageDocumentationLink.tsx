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

'use client';

import { useI18n } from '@/i18n/I18nProvider';
import { FiHelpCircle } from 'react-icons/fi';

interface PageDocumentationLinkProps {
  href: string;
  label: string;
}

export default function PageDocumentationLink({ href, label }: PageDocumentationLinkProps) {
  const { t } = useI18n();
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="shrink-0 text-gray-500 transition-colors hover:text-gray-700"
      aria-label={t("{value0} documentation", { value0: label })}
      title={t("Open {value0} documentation in a new tab", { value0: label })}
    >
      <FiHelpCircle className="h-6 w-6" />
    </a>
  );
}
