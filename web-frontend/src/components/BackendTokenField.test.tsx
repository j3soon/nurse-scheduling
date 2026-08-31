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

// This test is mostly AI generated.

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import BackendTokenField from '@/components/BackendTokenField';

const ENDPOINT = 'https://backend.example.test';

const renderField = (overrides: Partial<React.ComponentProps<typeof BackendTokenField>> = {}) => {
  const props = {
    endpoint: ENDPOINT,
    token: null,
    rememberToken: false,
    isEditing: false,
    onEdit: vi.fn(),
    onCancel: vi.fn(),
    onSave: vi.fn(),
    onClear: vi.fn(),
    ...overrides,
  };
  return { props, ...render(<BackendTokenField {...props} />) };
};

describe('BackendTokenField', () => {
  it('asks for a token when none is set', async () => {
    const user = userEvent.setup();
    const { props } = renderField();

    expect(screen.getByText('Token required')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: `Forget token for ${ENDPOINT}` })).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: `Enter token for ${ENDPOINT}` }));
    expect(props.onEdit).toHaveBeenCalled();
  });

  it('distinguishes a remembered token from a session-only token', () => {
    const { unmount } = renderField({ token: 'secret', rememberToken: true });
    expect(screen.getByText('Token saved on this device')).toBeInTheDocument();
    unmount();

    renderField({ token: 'secret', rememberToken: false });
    expect(screen.getByText('Token set for this session')).toBeInTheDocument();
  });

  it('prefills a remembered token so it can be corrected', () => {
    renderField({ token: 'secret', rememberToken: true, isEditing: true });

    expect(screen.getByLabelText(`Token for ${ENDPOINT}`)).toHaveValue('secret');
    expect(screen.getByRole('button', { name: `Save token for ${ENDPOINT}` })).toBeEnabled();
  });

  it('starts blank for a session-only token that is not stored anywhere', () => {
    renderField({ token: 'secret', rememberToken: false, isEditing: true });

    expect(screen.getByLabelText(`Token for ${ENDPOINT}`)).toHaveValue('');
    expect(screen.getByRole('button', { name: `Save token for ${ENDPOINT}` })).toBeDisabled();
  });

  it('starts blank when no token is set', () => {
    renderField({ isEditing: true });

    expect(screen.getByLabelText(`Token for ${ENDPOINT}`)).toHaveValue('');
  });

  it('saves a trimmed token with the chosen remember setting', async () => {
    const user = userEvent.setup();
    const { props } = renderField({ isEditing: true });

    await user.type(screen.getByLabelText(`Token for ${ENDPOINT}`), '  entered-token  ');
    await user.click(screen.getByRole('checkbox', { name: /remember on this device/i }));
    await user.click(screen.getByRole('button', { name: `Save token for ${ENDPOINT}` }));

    expect(props.onSave).toHaveBeenCalledWith('entered-token', true);
  });

  it('submits with Enter and cancels with Escape', async () => {
    const user = userEvent.setup();
    const { props } = renderField({ isEditing: true });

    const input = screen.getByLabelText(`Token for ${ENDPOINT}`);
    await user.type(input, 'entered-token{Enter}');
    expect(props.onSave).toHaveBeenCalledWith('entered-token', false);

    await user.type(input, '{Escape}');
    expect(props.onCancel).toHaveBeenCalled();
  });

  it('clears a stored token on request', async () => {
    const user = userEvent.setup();
    const { props } = renderField({ token: 'secret', rememberToken: true });

    await user.click(screen.getByRole('button', { name: `Forget token for ${ENDPOINT}` }));
    expect(props.onClear).toHaveBeenCalled();
  });

  it('disables the controls while an optimization is running', () => {
    renderField({ token: 'secret', rememberToken: true, disabled: true });

    expect(screen.getByRole('button', { name: `Change token for ${ENDPOINT}` })).toBeDisabled();
    expect(screen.getByRole('button', { name: `Forget token for ${ENDPOINT}` })).toBeDisabled();
  });
});
