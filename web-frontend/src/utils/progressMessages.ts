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

export type ProgressEvent = {
  type: 'phase' | 'solution' | 'completed' | 'failed';
  code: string;
  message: string;
  progress?: number;
  score?: number;
  solution_count?: number;
  elapsed_seconds?: number;
};

const PROGRESS_MESSAGES: Record<string, string> = {
  loading_scenario: '載入排班設定檔...',
  parsing_data: '解析設定資料...',
  initializing_solver: '初始化求解器...',
  creating_shift_variables: '建立排班變數...',
  creating_off_variables: '建立休假變數...',
  creating_lookup_maps: '建立快速查詢索引...',
  adding_preferences: '載入偏好與限制條件...',
  solving: '開始求解...',
  solution_found: '找到更好解',
  exporting: '準備排班結果...',
  schedule_completed: '排班完成，正在產生 Excel...',
  completed: '優化完成！',
  failed: '優化失敗',
};

export function formatProgressMessage(event: ProgressEvent): string {
  const label = PROGRESS_MESSAGES[event.code] ?? event.message;

  if (event.type === 'solution') {
    const details = [
      event.score !== undefined ? `分數 ${event.score}` : null,
      event.solution_count !== undefined ? `第 ${event.solution_count} 個解` : null,
      event.elapsed_seconds !== undefined ? `耗時 ${event.elapsed_seconds.toFixed(1)} 秒` : null,
    ].filter(Boolean);
    return details.length > 0 ? `${label}：${details.join('，')}` : label;
  }

  if (event.type === 'failed') {
    return `${label}：${event.message}`;
  }

  return label;
}
