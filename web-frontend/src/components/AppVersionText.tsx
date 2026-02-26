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

const HASH_PATTERN = /^[0-9a-fA-F]+$/;
const TAGGED_COMMIT_PATTERN = /^(?<tag>.+)(?<commitCount>-\d+)-g(?<hash>[0-9a-fA-F]+)$/;

type ParsedVersionParts = {
  tag: string;
  commitCount: string;
  hash?: string;
  dirtySuffix: string;
  isHashOnly: boolean;
};

function parseVersionParts(version: string): ParsedVersionParts {
  const dirtySuffix = version.endsWith('-dirty') ? '-dirty' : '';
  const baseVersion = dirtySuffix ? version.slice(0, -dirtySuffix.length) : version;

  if (HASH_PATTERN.test(baseVersion)) {
    return {
      tag: '',
      commitCount: '',
      hash: baseVersion,
      dirtySuffix,
      isHashOnly: true,
    };
  }

  const taggedCommitMatch = baseVersion.match(TAGGED_COMMIT_PATTERN)?.groups;
  if (taggedCommitMatch) {
    return {
      tag: taggedCommitMatch.tag,
      commitCount: taggedCommitMatch.commitCount,
      hash: taggedCommitMatch.hash,
      dirtySuffix,
      isHashOnly: false,
    };
  }

  return {
    tag: baseVersion,
    commitCount: '',
    dirtySuffix,
    isHashOnly: false,
  };
}

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
  // These are the only output types for "git describe --tags --always --dirty"
  const { tag, commitCount, hash, dirtySuffix, isHashOnly } = parseVersionParts(version);

  const tagNode = tag && versionHref ? (
    <a href={versionHref} target="_blank" rel="noopener noreferrer" className={versionClassName}>
      {tag}
    </a>
  ) : tag ? (
    <>{tag}</>
  ) : (
    null
  );

  if (!hash) {
    return (
      <>
        {tagNode}
        {commitCount}
      </>
    );
  }

  return (
    <>
      {tagNode}
      {commitCount}
      {!isHashOnly && '-g'}
      <a
        href={`${GITHUB_REPO_URL}/tree/${hash}`}
        target="_blank"
        rel="noopener noreferrer"
        className={commitClassName ?? versionClassName}
      >
        {hash}
      </a>
      {dirtySuffix}
    </>
  );
}
