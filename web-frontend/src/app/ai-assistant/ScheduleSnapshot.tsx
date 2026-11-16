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

import { useState } from 'react';
import { useI18n } from '@/i18n/I18nProvider';

// Keep the saved YAML exact, including comments and its final newline.
export default function ScheduleSnapshot({ yaml }: { yaml: string }) {
  const { t } = useI18n();
  const [copyStatus, setCopyStatus] = useState('Copy YAML');
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(yaml);
      setCopyStatus('Copied');
    } catch {
      setCopyStatus('Copy failed. Select the YAML to copy it.');
    }
  };
  return (
    <details className="system-prompt schedule-snapshot">
      <summary className="collapsed-summary">{t("View Schedule Spec YAML")}</summary>
      <div className="snapshot-actions">
        <button type="button" data-live-action="copy-schedule" onClick={() => void copy()}>{t(copyStatus)}</button>
        <a download="schedule-spec.yaml" href={`data:application/yaml;charset=utf-8,${encodeURIComponent(yaml)}`}>{t("Download YAML")}</a>
      </div>
      <pre className="collapsed-output"><code>{yaml}</code></pre>
    </details>
  );
}
