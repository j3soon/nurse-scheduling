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

'use client';

import { usePathname } from 'next/navigation';
import AppVersionText from '@/components/AppVersionText';
import {
  AGPL_LICENSE_URL,
  GITHUB_ACKNOWLEDGMENTS_URL,
  GITHUB_AUTHOR_URL,
  GITHUB_CODE_FREQUENCY_URL,
  GITHUB_LICENSE_URL,
  GITHUB_PRIVACY_URL,
  GITHUB_REPO_URL,
  GITHUB_TAGS_URL,
} from '@/constants/urls';
import { CURRENT_APP_VERSION } from '@/utils/version';

export default function Footer() {
  const pathname = usePathname();
  if (pathname === '/experimental-ai') return null;

  return (
    <footer style={{ textAlign: 'center', padding: '1.5rem', marginTop: '2rem', fontSize: '0.875rem', color: 'gray' }}>
      <div>
        <a href={GITHUB_LICENSE_URL} target="_blank" rel="noopener noreferrer" className="footer-link">Copyright ©</a>{' '}
        <a href={GITHUB_CODE_FREQUENCY_URL} target="_blank" rel="noopener noreferrer" className="footer-link">2023-{new Date().getFullYear()}</a>{' '}
        <a href={GITHUB_AUTHOR_URL} target="_blank" rel="noopener noreferrer" className="footer-link">Johnson Sun</a> &{' '}
        <a href={GITHUB_ACKNOWLEDGMENTS_URL} target="_blank" rel="noopener noreferrer" className="footer-link">Contributors</a>.{' '}
        <a href={GITHUB_PRIVACY_URL} target="_blank" rel="noopener noreferrer" className="footer-link">Privacy Policy</a>.
      </div>
      <div>
        <a href={GITHUB_REPO_URL} target="_blank" rel="noopener noreferrer" className="footer-link">Nurse Scheduling Project</a>{' '}
        <AppVersionText
          version={CURRENT_APP_VERSION}
          versionHref={GITHUB_TAGS_URL}
          versionClassName="footer-link"
          commitClassName="footer-link"
        />
        .{' '}Licensed under{' '}
        <a href={AGPL_LICENSE_URL} target="_blank" rel="noopener noreferrer" className="footer-link">AGPL-3.0</a>.
      </div>
    </footer>
  );
}
