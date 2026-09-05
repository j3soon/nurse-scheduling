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

import { FiStar } from 'react-icons/fi';
import { GITHUB_REPO_URL } from '@/constants/urls';

export default function StarRepoNudge() {
  return (
    <div className="flex items-center gap-2 rounded-md border border-blue-100 bg-blue-50 px-3 py-2 text-sm text-gray-600">
      <FiStar className="h-4 w-4 shrink-0 text-blue-600" aria-hidden="true" />
      <p>
        Finding this useful?{' '}
        <a
          href={GITHUB_REPO_URL}
          target="_blank"
          rel="noopener noreferrer"
          className="font-medium text-blue-700 underline underline-offset-2 hover:text-blue-900"
        >
          Star the project on GitHub
        </a>
        .
      </p>
    </div>
  );
}
