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

import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ShiftPreferenceEditor from '@/components/ShiftPreferenceEditor';

describe('ShiftPreferenceEditor', () => {
  const shiftTypes = [
    { id: 'D', description: 'Day' },
    { id: 'N', description: 'Night' },
  ];

  it('does not render when closed', () => {
    render(
      <ShiftPreferenceEditor
        isOpen={false}
        onClose={vi.fn()}
        onSave={vi.fn()}
        personId="P1"
        dateId="01"
        shiftTypes={shiftTypes}
        initialPreferences={[]}
      />,
    );

    expect(screen.queryByText('Shift Preference Matrix')).not.toBeInTheDocument();
  });

  it('blocks save when an invalid weight value is entered', () => {
    const onSave = vi.fn();
    const onClose = vi.fn();

    render(
      <ShiftPreferenceEditor
        isOpen={true}
        onClose={onClose}
        onSave={onSave}
        personId="P1"
        dateId="01"
        shiftTypes={shiftTypes}
        initialPreferences={[{ shiftTypeId: 'D', weight: 1 }]}
      />,
    );

    const inputs = screen.getAllByRole('textbox');
    fireEvent.change(inputs[0], { target: { value: 'abc' } });
    fireEvent.click(screen.getByRole('button', { name: /save preferences/i }));

    expect(onSave).not.toHaveBeenCalled();
    expect(onClose).not.toHaveBeenCalled();
  });

  it('saves updated preferences and supports clear all', () => {
    const onSave = vi.fn();
    const onClose = vi.fn();

    render(
      <ShiftPreferenceEditor
        isOpen={true}
        onClose={onClose}
        onSave={onSave}
        personId="P1"
        dateId="01"
        shiftTypes={shiftTypes}
        initialPreferences={[]}
      />,
    );

    fireEvent.click(screen.getAllByRole('button', { name: '+∞' })[0]);
    fireEvent.click(screen.getByRole('button', { name: /save preferences/i }));

    expect(onSave).toHaveBeenCalledWith([{ shiftTypeId: 'D', weight: Infinity }]);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('clears all preferences before save', () => {
    const onSave = vi.fn();

    render(
      <ShiftPreferenceEditor
        isOpen={true}
        onClose={vi.fn()}
        onSave={onSave}
        personId="P1"
        dateId="01"
        shiftTypes={shiftTypes}
        initialPreferences={[{ shiftTypeId: 'D', weight: 3 }, { shiftTypeId: 'N', weight: -2 }]}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /clear all/i }));
    fireEvent.click(screen.getByRole('button', { name: /save preferences/i }));

    expect(onSave).toHaveBeenCalledWith([]);
  });

  it('supports negative infinity shortcut and saves via Enter key', () => {
    const onSave = vi.fn();
    const onClose = vi.fn();

    render(
      <ShiftPreferenceEditor
        isOpen={true}
        onClose={onClose}
        onSave={onSave}
        personId="P1"
        dateId="01"
        shiftTypes={shiftTypes}
        initialPreferences={[]}
      />,
    );

    fireEvent.click(screen.getAllByRole('button', { name: '-∞' })[1]);
    fireEvent.keyDown(document, { key: 'Enter' });

    expect(onSave).toHaveBeenCalledWith([{ shiftTypeId: 'N', weight: -Infinity }]);
    expect(onClose).toHaveBeenCalled();
  });

  it('cancels with Escape and resets unsaved draft state', async () => {
    const user = userEvent.setup();
    const onSave = vi.fn();
    const onClose = vi.fn();

    const { rerender } = render(
      <ShiftPreferenceEditor
        isOpen={true}
        onClose={onClose}
        onSave={onSave}
        personId="P1"
        dateId="01"
        shiftTypes={shiftTypes}
        initialPreferences={[]}
      />,
    );

    await user.click(screen.getAllByRole('button', { name: '+∞' })[0]);
    expect(screen.getByText('Active Preferences Summary')).toBeInTheDocument();

    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onSave).not.toHaveBeenCalled();
    expect(onClose).toHaveBeenCalled();

    rerender(
      <ShiftPreferenceEditor
        isOpen={true}
        onClose={onClose}
        onSave={onSave}
        personId="P1"
        dateId="01"
        shiftTypes={shiftTypes}
        initialPreferences={[]}
      />,
    );

    expect(screen.queryByText('Active Preferences Summary')).not.toBeInTheDocument();
  });

  it('removes a preference when its weight is changed back to zero', () => {
    const onSave = vi.fn();

    render(
      <ShiftPreferenceEditor
        isOpen={true}
        onClose={vi.fn()}
        onSave={onSave}
        personId="P1"
        dateId="01"
        shiftTypes={shiftTypes}
        initialPreferences={[{ shiftTypeId: 'D', weight: 3 }]}
      />,
    );

    const inputs = screen.getAllByRole('textbox');
    fireEvent.change(inputs[0], { target: { value: '0' } });
    fireEvent.click(screen.getByRole('button', { name: /save preferences/i }));

    expect(onSave).toHaveBeenCalledWith([]);
  });

  it('reopens with initial preferences after canceling unsaved changes', async () => {
    const user = userEvent.setup();
    const { rerender } = render(
      <ShiftPreferenceEditor
        isOpen={true}
        onClose={vi.fn()}
        onSave={vi.fn()}
        personId="P1"
        dateId="01"
        shiftTypes={shiftTypes}
        initialPreferences={[{ shiftTypeId: 'D', weight: 3 }]}
      />,
    );

    const inputs = screen.getAllByRole('textbox');
    fireEvent.change(inputs[0], { target: { value: '9' } });
    await user.click(screen.getByRole('button', { name: /cancel/i }));

    rerender(
      <ShiftPreferenceEditor
        isOpen={true}
        onClose={vi.fn()}
        onSave={vi.fn()}
        personId="P1"
        dateId="01"
        shiftTypes={shiftTypes}
        initialPreferences={[{ shiftTypeId: 'D', weight: 3 }]}
      />,
    );

    expect(screen.getAllByRole('textbox')[0]).toHaveValue('3');
  });

  it('updates an existing draft preference instead of duplicating it before save', () => {
    const onSave = vi.fn();

    render(
      <ShiftPreferenceEditor
        isOpen={true}
        onClose={vi.fn()}
        onSave={onSave}
        personId="P1"
        dateId="01"
        shiftTypes={shiftTypes}
        initialPreferences={[{ shiftTypeId: 'D', weight: 1 }]}
      />,
    );

    const inputs = screen.getAllByRole('textbox');
    fireEvent.change(inputs[0], { target: { value: '4' } });
    fireEvent.change(inputs[0], { target: { value: '6' } });
    fireEvent.click(screen.getByRole('button', { name: /save preferences/i }));

    expect(onSave).toHaveBeenCalledWith([{ shiftTypeId: 'D', weight: 6 }]);
  });
});
