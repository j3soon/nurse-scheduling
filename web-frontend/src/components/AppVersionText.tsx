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

import { GITHUB_REPO_URL } from '@/constants/urls';
import { parseVersionParts } from '@/utils/version';

type AppVersionTextProps = {
  version: string;
  versionHref?: string;
  versionClassName?: string;
  commitClassName?: string;
};

export default function AppVersionText({
  version,
  versionHref,
  versionClassName,
  commitClassName,
}: AppVersionTextProps) {
  // We may receive multiple version string formats, e.g.:
  // - v0.1.2-20-gxxxxxxx-dirty
  // - v0.1.1-10-gxxxxxxx
  // - v0.1.1
  // - v0.1.0
  // - v0.1.0-dirty
  // - xxxxxxx
  // - xxxxxxx-dirty
  // These are the only output types for "git describe --tags --always --dirty" with vX.Y.Z tags.
  const { major, minor, patch, commitsAfterTag, commitId, dirty } = parseVersionParts(version);
  const tag = major !== null && minor !== null && patch !== null ? `v${major}.${minor}.${patch}` : '';
  const isHashOnly = major === null && minor === null && patch === null;
  const dirtySuffix = dirty ? '-dirty' : '';

  const tagNode = tag && versionHref ? (
    <a href={versionHref} target="_blank" rel="noopener noreferrer" className={versionClassName}>
      {tag}
    </a>
  ) : tag ? (
    <>{tag}</>
  ) : (
    null
  );

  if (!commitId) {
    return (
      <>
        {tagNode ?? version}
      </>
    );
  }

  return (
    <>
      {tagNode}
      {!isHashOnly && `-${commitsAfterTag}-g`}
      <a
        href={`${GITHUB_REPO_URL}/tree/${commitId}`}
        target="_blank"
        rel="noopener noreferrer"
        className={commitClassName ?? versionClassName}
      >
        {commitId}
      </a>
      {dirtySuffix}
    </>
  );
}
