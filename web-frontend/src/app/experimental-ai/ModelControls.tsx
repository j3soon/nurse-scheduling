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

import { useEffect, useRef, useState } from 'react';
import { getModels, type AvailableModel, type ModelSelection } from './aiClient';

export function ModelControls({ endpoint, token, disabled, onChange }: {
  endpoint: string; token: string | null; disabled: boolean;
  onChange: (selection: ModelSelection | undefined) => void;
}) {
  const [models, setModels] = useState<AvailableModel[]>([]);
  const [selection, setSelection] = useState<ModelSelection>();
  const [error, setError] = useState<string>();
  const [reload, setReload] = useState(0);
  const [loadedScope, setLoadedScope] = useState<string>();
  const choices = useRef(new Map<string, ModelSelection>());
  const scope = `${endpoint}\n${token ?? ''}`;
  const requestScope = `${scope}\n${reload}`;
  const ready = loadedScope === requestScope;
  const model = models.find(item => item.id === selection?.model);
  useEffect(() => {
    const controller = new AbortController();
    onChange(undefined);
    getModels(controller.signal, token, endpoint).then(result => {
      if (controller.signal.aborted) return;
      const saved = choices.current.get(scope);
      const selected = result.models.find(item => item.id === saved?.model)
        ?? result.models.find(item => item.id === result.default_model) ?? result.models[0];
      if (!selected) throw new Error('No compatible chat models are available to this AI key.');
      const reasoning = selected.reasoning_options.some(option => option.id === saved?.reasoning) ? saved!.reasoning : selected.default_reasoning;
      const next = { model: selected.id, reasoning };
      setModels(result.models);
      setSelection(next);
      setLoadedScope(requestScope);
      setError(undefined);
      onChange(next);
    }).catch((failure: unknown) => {
      if (!controller.signal.aborted) {
        setError(failure instanceof Error ? failure.message : 'Could not load AI models.');
      }
    });
    return () => controller.abort();
  }, [endpoint, token, scope, requestScope, onChange]);

  const select = (next: ModelSelection) => {
    choices.current.set(`${scope}\n${next.model}`, next);
    choices.current.set(scope, next);
    setSelection(next);
    onChange(next);
  };
  return <div className="flex flex-wrap items-center gap-3 px-2 text-xs text-gray-700">
    <label className="flex min-w-0 max-w-full items-center gap-2">Model
      <select aria-label="AI model" className="min-w-0 max-w-64 rounded-lg border border-gray-300 bg-white p-2"
        disabled={disabled || !ready || !!error} value={selection?.model ?? ''}
        onChange={event => {
          const target = models.find(item => item.id === event.target.value)!;
          const saved = choices.current.get(`${scope}\n${target.id}`);
          select({ model: target.id, reasoning: target.reasoning_options.some(option => option.id === saved?.reasoning) ? saved!.reasoning : target.default_reasoning });
        }}>
        {!selection && <option value="">Loading models…</option>}
        {models.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
      </select>
    </label>
    {model && model.reasoning_options.length > 1 && <label className="flex items-center gap-2">Reasoning
      <select aria-label="Reasoning" className="rounded-lg border border-gray-300 bg-white p-2"
        disabled={disabled || !ready || !!error} value={selection?.reasoning}
        onChange={event => select({ model: model.id, reasoning: event.target.value })}>
        {model.reasoning_options.map(option => <option key={option.id} value={option.id}>{option.label}</option>)}
      </select>
    </label>}
    {error && <span role="alert">{error} <button type="button" className="underline" onClick={() => setReload(value => value + 1)}>Retry</button></span>}
  </div>;
}
