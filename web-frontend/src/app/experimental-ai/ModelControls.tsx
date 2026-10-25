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
import { getModels, getSessionModelSelection, updateSessionModelSelection, type AvailableModel, type ModelSelection } from './aiClient';

export function ModelControls({
  endpoint, token, disabled, modelLocked = false, runActive = false, sessionId = null, onChange,
}: {
  endpoint: string; token: string | null; disabled: boolean;
  sessionId?: string | null;
  // Lock while a message that the server may still accept is in flight.
  modelLocked?: boolean;
  // A run can fix the model on the server, so each run state change re-reads the saved lock.
  runActive?: boolean;
  onChange: (selection: ModelSelection | undefined) => void;
}) {
  const [models, setModels] = useState<AvailableModel[]>([]);
  const [selection, setSelection] = useState<ModelSelection>();
  const [savedLock, setSavedLock] = useState(false);
  // Each run state change requests a new read of the saved lock. Keep the model fixed until it finishes.
  const [lockRunState, setLockRunState] = useState(runActive);
  const [lockReads, setLockReads] = useState(0);
  const [finishedLockReads, setFinishedLockReads] = useState(0);
  if (lockRunState !== runActive) {
    setLockRunState(runActive);
    setLockReads(reads => reads + 1);
  }
  const [error, setError] = useState<string>();
  const [saving, setSaving] = useState(false);
  const [reload, setReload] = useState(0);
  const [loadedScope, setLoadedScope] = useState<string>();
  const choices = useRef(new Map<string, ModelSelection>());
  const pendingChoices = useRef(new Map<string, ModelSelection>());
  const saves = useRef(Promise.resolve());
  const generation = useRef(0);
  const latestChange = useRef(0);
  const scope = `${endpoint}\n${token ?? ''}`;
  const requestScope = `${scope}\n${sessionId ?? ''}\n${reload}`;
  const ready = loadedScope === requestScope;
  const model = models.find(item => item.id === selection?.model);
  const locked = modelLocked || savedLock || (sessionId !== null && finishedLockReads !== lockReads);
  useEffect(() => {
    const controller = new AbortController();
    generation.current += 1;
    saves.current = Promise.resolve();
    onChange(undefined);
    Promise.all([
      getModels(controller.signal, token, endpoint),
      sessionId ? getSessionModelSelection(sessionId, controller.signal, token, endpoint) : Promise.resolve(null),
    ]).then(async ([result, stored]) => {
      if (controller.signal.aborted) return;
      const current = stored?.selection;
      const pending = pendingChoices.current.get(scope);
      const saved = pending ?? current ?? choices.current.get(scope);
      const selected = result.models.find(item => item.id === saved?.model)
        ?? result.models.find(item => item.id === result.default_model) ?? result.models[0];
      if (!selected) throw new Error('No compatible chat models are available to this AI key.');
      const reasoning = selected.reasoning_options.some(option => option.id === saved?.reasoning) ? saved!.reasoning : selected.default_reasoning;
      let next = { model: selected.id, reasoning };
      if (sessionId && pending) {
        if (next.model !== current?.model || next.reasoning !== current?.reasoning) {
          setSaving(true);
          next = (await updateSessionModelSelection(sessionId, next, token, endpoint)).selection;
          if (controller.signal.aborted) return;
        }
        pendingChoices.current.delete(scope);
      }
      setModels(result.models);
      setSelection(next);
      setSavedLock(stored?.locked ?? false);
      setLoadedScope(requestScope);
      setError(undefined);
      setSaving(false);
      choices.current.set(scope, next);
      onChange(next);
    }).catch((failure: unknown) => {
      if (!controller.signal.aborted) {
        setSaving(false);
        setError(failure instanceof Error ? failure.message : 'Could not load AI models.');
      }
    });
    return () => { controller.abort(); generation.current += 1; };
  }, [endpoint, token, sessionId, scope, requestScope, onChange]);

  useEffect(() => {
    if (!sessionId || lockReads === 0) return;
    const controller = new AbortController();
    getSessionModelSelection(sessionId, controller.signal, token, endpoint).then(stored => {
      if (controller.signal.aborted) return;
      setSavedLock(stored.locked);
      setFinishedLockReads(lockReads);
    }, () => {
      // Keep the last saved lock. The backend still rejects a change to a fixed model.
      if (!controller.signal.aborted) setFinishedLockReads(lockReads);
    });
    return () => controller.abort();
  }, [endpoint, token, sessionId, lockReads]);

  const select = (next: ModelSelection) => {
    choices.current.set(`${scope}\n${next.model}`, next);
    choices.current.set(scope, next);
    setSelection(next);
    if (!sessionId) {
      pendingChoices.current.set(scope, next);
      onChange(next);
      return;
    }
    onChange(undefined);
    setSaving(true);
    const currentGeneration = generation.current;
    const change = ++latestChange.current;
    // Keep writes in selection order even when a previous request responds slowly.
    saves.current = saves.current.then(async () => {
      const saved = await updateSessionModelSelection(sessionId, next, token, endpoint);
      if (generation.current === currentGeneration && change === latestChange.current) {
        setError(undefined);
        setSaving(false);
        setSavedLock(saved.locked);
        onChange(saved.selection);
      }
    }).catch((failure: unknown) => {
      if (generation.current === currentGeneration && change === latestChange.current) {
        setSaving(false);
        setError(failure instanceof Error ? failure.message : 'Could not save the model choice.');
      }
    });
  };
  return <div className="flex flex-wrap items-center gap-3 px-2 text-xs text-gray-700">
    <label className="flex min-w-0 max-w-full items-center gap-2">Model
      <select aria-label="AI model" className="min-w-0 max-w-64 rounded-lg border border-gray-300 bg-white p-2"
        disabled={disabled || locked || !ready || !!error} value={selection?.model ?? ''}
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
    {saving && <span role="status">Saving model choice…</span>}
    <span className="text-gray-500">{locked
      ? 'Model fixed for this conversation. Reasoning changes apply to future turns.'
      : 'Choose a model before the first message.'}</span>
  </div>;
}
