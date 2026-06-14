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

import { fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ShiftRequestsPage from '@/app/shift-requests/page';
import { UnsavedEditingStateProvider } from '@/utils/unsavedEditingState';

const mockUseSchedulingData = vi.hoisted(() => vi.fn());
const fileContentsByName = new Map<string, string>();

class MockResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}

class MockFileReader {
  onload: ((ev: ProgressEvent<FileReader>) => unknown) | null = null;

  readAsText(file: File) {
    const content = fileContentsByName.get(file.name) || '';
    this.onload?.({ target: { result: content } } as unknown as ProgressEvent<FileReader>);
  }
}

vi.mock('@/hooks/useSchedulingData', () => ({
  useSchedulingData: mockUseSchedulingData,
}));

vi.mock('@/components/UploadButton', () => ({
  __esModule: true,
  default: ({ onFileUpload, buttonText, disabled }: { onFileUpload: (file: File) => void; buttonText: string; disabled?: boolean }) => (
    <button
      onClick={() => onFileUpload(new File(['ignored'], buttonText === 'Upload Shift Requests' ? 'shift-requests.csv' : 'people-history.csv', { type: 'text/csv' }))}
      disabled={disabled}
    >
      {buttonText}
    </button>
  ),
}));

function renderShiftRequestsPage() {
  return render(
    <UnsavedEditingStateProvider>
      <ShiftRequestsPage />
    </UnsavedEditingStateProvider>
  );
}

describe('ShiftRequestsPage CSV parsing validation', () => {
  const reorderItems = vi.fn();
  const updatePreferencesByType = vi.fn();

  beforeEach(() => {
    vi.stubGlobal('ResizeObserver', MockResizeObserver as unknown as typeof ResizeObserver);
    vi.stubGlobal('FileReader', MockFileReader as unknown as typeof FileReader);
    vi.spyOn(window, 'alert').mockImplementation(() => undefined);
    vi.spyOn(window, 'confirm').mockImplementation(() => true);
    reorderItems.mockReset();
    updatePreferencesByType.mockReset();

    mockUseSchedulingData.mockReturnValue({
      dateData: {
        range: {
          startDate: new Date('2026-01-01T12:00:00.000Z'),
          endDate: new Date('2026-01-01T12:00:00.000Z'),
        },
        items: [{ id: '01', description: 'Jan 1' }],
        groups: [{ id: 'ALL_DATES', members: ['01'], description: '' }],
      },
      peopleData: {
        items: [{ id: 'Person 1', description: '', history: [] }],
        groups: [{ id: 'ALL_PEOPLE', members: ['Person 1'], description: '' }],
        history: [],
      },
      shiftTypeData: {
        items: [{ id: 'D', description: 'Day' }],
        groups: [{ id: 'ALL_SHIFT_TYPES', members: ['D'], description: '' }],
      },
      getPreferencesByType: vi.fn(() => []),
      updatePreferencesByType,
      addPersonHistory: vi.fn(),
      updatePersonHistory: vi.fn(),
      reorderItems,
    });
  });

  it('shows validation error for malformed people-history CSV upload', async () => {
    const user = userEvent.setup();
    fileContentsByName.set('people-history.csv', 'Person 1,D\n');

    renderShiftRequestsPage();

    await user.click(screen.getByRole('button', { name: /quick add preference/i }));
    fireEvent.click(screen.getByRole('button', { name: /upload people history \(shorthand\)/i }));

    expect(alert).toHaveBeenCalledWith(
      expect.stringContaining('CSV validation failed: Row 1 should have 3 columns'),
    );
  });

  it('processes valid people-history CSV and updates people history', async () => {
    const user = userEvent.setup();
    fileContentsByName.set('people-history.csv', 'Person 1,D,2\n');

    renderShiftRequestsPage();

    await user.click(screen.getByRole('button', { name: /quick add preference/i }));
    fireEvent.click(screen.getByRole('button', { name: /upload people history \(shorthand\)/i }));

    expect(reorderItems).toHaveBeenCalledTimes(1);
    expect(reorderItems).toHaveBeenCalledWith(
      'people',
      expect.objectContaining({
        items: [expect.objectContaining({ id: 'Person 1', history: ['D', 'D'] })],
      }),
      [expect.objectContaining({ id: 'Person 1', history: ['D', 'D'] })],
    );
    expect(alert).toHaveBeenCalledWith('Successfully processed 1 shift type entries from people history CSV!');
  });

  it('alerts when the uploaded people-history file has no content', async () => {
    const user = userEvent.setup();
    fileContentsByName.set('people-history.csv', '');

    renderShiftRequestsPage();

    await user.click(screen.getByRole('button', { name: /quick add preference/i }));
    fireEvent.click(screen.getByRole('button', { name: /upload people history \(shorthand\)/i }));

    expect(alert).toHaveBeenCalledWith('No content found in the uploaded file.');
    expect(reorderItems).not.toHaveBeenCalled();
  });

  it('processes valid shift-requests matrix CSV and updates preferences', async () => {
    const user = userEvent.setup();
    fileContentsByName.set('shift-requests.csv', 'Person 1,D\n');

    renderShiftRequestsPage();

    await user.click(screen.getByRole('button', { name: /quick add preference/i }));

    const weightInput = screen.getByPlaceholderText('Enter weight (positive for preference, negative for avoidance, or Infinity/-Infinity)');
    fireEvent.change(weightInput, { target: { value: '2' } });

    fireEvent.click(screen.getByRole('button', { name: /upload shift requests/i }));

    expect(updatePreferencesByType).toHaveBeenCalledWith(
      'shift request',
      [
        {
          type: 'shift request',
          person: ['Person 1'],
          date: ['01'],
          shiftType: ['D'],
          weight: 2,
        },
      ],
      undefined,
    );
    expect(alert).toHaveBeenCalledWith('Successfully processed CSV file with 1 shift preferences!');
  });

  it('alerts when the uploaded shift-requests file has no content', async () => {
    const user = userEvent.setup();
    fileContentsByName.set('shift-requests.csv', '');

    renderShiftRequestsPage();

    await user.click(screen.getByRole('button', { name: /quick add preference/i }));
    fireEvent.change(
      screen.getByPlaceholderText('Enter weight (positive for preference, negative for avoidance, or Infinity/-Infinity)'),
      { target: { value: '2' } },
    );
    fireEvent.click(screen.getByRole('button', { name: /upload shift requests/i }));

    expect(alert).toHaveBeenCalledWith('No content found in the uploaded file.');
    expect(updatePreferencesByType).not.toHaveBeenCalled();
  });

  it('shows validation error for invalid person IDs in shift-requests CSV', async () => {
    const user = userEvent.setup();
    fileContentsByName.set('shift-requests.csv', 'Unknown,D\n');

    renderShiftRequestsPage();

    await user.click(screen.getByRole('button', { name: /quick add preference/i }));
    fireEvent.change(
      screen.getByPlaceholderText('Enter weight (positive for preference, negative for avoidance, or Infinity/-Infinity)'),
      { target: { value: '2' } },
    );
    fireEvent.click(screen.getByRole('button', { name: /upload shift requests/i }));

    expect(alert).toHaveBeenCalledWith(
      expect.stringContaining('CSV validation failed: Row 1 has invalid person ID "Unknown"'),
    );
    expect(updatePreferencesByType).not.toHaveBeenCalled();
  });

  it('recovers from an invalid shift-requests CSV upload and then accepts a valid one', async () => {
    const user = userEvent.setup();

    renderShiftRequestsPage();

    await user.click(screen.getByRole('button', { name: /quick add preference/i }));
    fireEvent.change(
      screen.getByPlaceholderText('Enter weight (positive for preference, negative for avoidance, or Infinity/-Infinity)'),
      { target: { value: '2' } },
    );

    fileContentsByName.set('shift-requests.csv', 'Unknown,D\n');
    fireEvent.click(screen.getByRole('button', { name: /upload shift requests/i }));

    expect(alert).toHaveBeenCalledWith(
      expect.stringContaining('CSV validation failed: Row 1 has invalid person ID "Unknown"'),
    );
    expect(updatePreferencesByType).not.toHaveBeenCalled();

    fileContentsByName.set('shift-requests.csv', 'Person 1,D\n');
    fireEvent.click(screen.getByRole('button', { name: /upload shift requests/i }));

    expect(updatePreferencesByType).toHaveBeenCalledWith(
      'shift request',
      [
        {
          type: 'shift request',
          person: ['Person 1'],
          date: ['01'],
          shiftType: ['D'],
          weight: 2,
        },
      ],
      undefined,
    );
    expect(alert).toHaveBeenCalledWith('Successfully processed CSV file with 1 shift preferences!');
  });

  it('shows validation error for duplicate person rows in people-history CSV', async () => {
    const user = userEvent.setup();

    mockUseSchedulingData.mockReturnValue({
      dateData: {
        range: {
          startDate: new Date('2026-01-01T12:00:00.000Z'),
          endDate: new Date('2026-01-01T12:00:00.000Z'),
        },
        items: [{ id: '01', description: 'Jan 1' }],
        groups: [{ id: 'ALL_DATES', members: ['01'], description: '' }],
      },
      peopleData: {
        items: [
          { id: 'Person 1', description: '', history: [] },
          { id: 'Person 2', description: '', history: [] },
        ],
        groups: [{ id: 'ALL_PEOPLE', members: ['Person 1', 'Person 2'], description: '' }],
        history: [],
      },
      shiftTypeData: {
        items: [{ id: 'D', description: 'Day' }],
        groups: [{ id: 'ALL_SHIFT_TYPES', members: ['D'], description: '' }],
      },
      getPreferencesByType: vi.fn(() => []),
      updatePreferencesByType,
      addPersonHistory: vi.fn(),
      updatePersonHistory: vi.fn(),
      reorderItems,
    });

    fileContentsByName.set('people-history.csv', 'Person 1,D,1\nPerson 1,D,2\n');

    renderShiftRequestsPage();

    await user.click(screen.getByRole('button', { name: /quick add preference/i }));
    fireEvent.click(screen.getByRole('button', { name: /upload people history \(shorthand\)/i }));

    expect(alert).toHaveBeenCalledWith(
      expect.stringContaining('CSV validation failed: Duplicate person ID "Person 1" found at row 2'),
    );
    expect(reorderItems).not.toHaveBeenCalled();
  });

  it('allows shift-requests upload when weight is zero', async () => {
    const user = userEvent.setup();
    fileContentsByName.set('shift-requests.csv', 'Person 1,D\n');

    renderShiftRequestsPage();

    await user.click(screen.getByRole('button', { name: /quick add preference/i }));
    fireEvent.change(
      screen.getByPlaceholderText('Enter weight (positive for preference, negative for avoidance, or Infinity/-Infinity)'),
      { target: { value: '0' } },
    );
    await user.click(screen.getByRole('checkbox', { name: 'D' }));
    const uploadButton = screen.getByRole('button', { name: /upload shift requests/i });
    expect(uploadButton).toBeEnabled();

    fireEvent.click(uploadButton);

    expect(updatePreferencesByType).toHaveBeenCalledWith(
      'shift request',
      [],
      undefined,
    );
  });

  it('updates shift-request upload availability as the quick-add weight moves between invalid, valid, and zero values', async () => {
    const user = userEvent.setup();

    renderShiftRequestsPage();

    await user.click(screen.getByRole('button', { name: /quick add preference/i }));
    const weightInput = screen.getByPlaceholderText('Enter weight (positive for preference, negative for avoidance, or Infinity/-Infinity)');
    const uploadButton = screen.getByRole('button', { name: /upload shift requests/i });

    fireEvent.change(weightInput, { target: { value: 'not-a-number' } });
    expect(uploadButton).toBeDisabled();

    fireEvent.change(weightInput, { target: { value: '2' } });
    expect(uploadButton).toBeEnabled();

    await user.click(screen.getByRole('checkbox', { name: 'D' }));
    fireEvent.change(weightInput, { target: { value: '0' } });
    expect(uploadButton).toBeEnabled();

    fireEvent.change(weightInput, { target: { value: '-Infinity' } });
    expect(uploadButton).toBeEnabled();
  });

  it('shows quick-add no-op warnings while keeping implicit clear behavior', async () => {
    const user = userEvent.setup();
    const existingPreferences = [
      {
        type: 'shift request',
        person: ['Person 1'],
        date: ['01'],
        shiftType: ['D'],
        weight: 2,
      },
    ];
    mockUseSchedulingData.mockReturnValue({
      dateData: {
        range: {
          startDate: new Date('2026-01-01T12:00:00.000Z'),
          endDate: new Date('2026-01-01T12:00:00.000Z'),
        },
        items: [{ id: '01', description: 'Jan 1' }],
        groups: [{ id: 'ALL_DATES', members: ['01'], description: '' }],
      },
      peopleData: {
        items: [{ id: 'Person 1', description: '', history: [] }],
        groups: [{ id: 'ALL_PEOPLE', members: ['Person 1'], description: '' }],
        history: [],
      },
      shiftTypeData: {
        items: [{ id: 'D', description: 'Day' }],
        groups: [{ id: 'ALL_SHIFT_TYPES', members: ['D'], description: '' }],
      },
      getPreferencesByType: vi.fn(() => existingPreferences),
      updatePreferencesByType,
      addPersonHistory: vi.fn(),
      updatePersonHistory: vi.fn(),
      reorderItems,
    });

    const { container } = renderShiftRequestsPage();

    await user.click(screen.getByRole('button', { name: /quick add preference/i }));
    const uploadButton = screen.getByRole('button', { name: /upload shift requests/i });
    const weightInput = screen.getByPlaceholderText('Enter weight (positive for preference, negative for avoidance, or Infinity/-Infinity)');
    const requestCell = container.querySelector('td[title="Click or drag to update preferences for Person 1 on date 01"]') as HTMLTableCellElement;

    expect(screen.getByText('Drag over cells to clear existing requests or history. Empty cells will not change.')).toBeInTheDocument();
    fireEvent.change(weightInput, { target: { value: '0' } });
    expect(uploadButton).toBeEnabled();
    fireEvent.mouseDown(requestCell, { button: 0 });
    fireEvent.mouseUp(requestCell, { button: 0 });
    expect(updatePreferencesByType).toHaveBeenCalledWith('shift request', [], { replaceLatestHistoryEntry: false });

    updatePreferencesByType.mockClear();
    await user.click(screen.getByRole('checkbox', { name: 'D' }));
    expect(screen.getByText('Drag over cells to remove D. Empty cells without it will not change.')).toBeInTheDocument();
    fireEvent.mouseDown(requestCell, { button: 0 });
    fireEvent.mouseUp(requestCell, { button: 0 });
    expect(updatePreferencesByType).toHaveBeenCalledWith('shift request', [], { replaceLatestHistoryEntry: false });

    updatePreferencesByType.mockClear();
    fireEvent.change(weightInput, { target: { value: 'not-a-number' } });
    expect(uploadButton).toBeDisabled();
    fireEvent.mouseDown(requestCell, { button: 0 });
    fireEvent.mouseUp(requestCell, { button: 0 });
    expect(updatePreferencesByType).not.toHaveBeenCalled();

    await user.click(screen.getByRole('checkbox', { name: 'D' }));
    fireEvent.mouseDown(requestCell, { button: 0 });
    fireEvent.mouseUp(requestCell, { button: 0 });
    expect(updatePreferencesByType).toHaveBeenCalledWith('shift request', [], { replaceLatestHistoryEntry: false });
  });

  it('clears multiple occupied history slots during one clear-mode drag gesture', async () => {
    const user = userEvent.setup();
    const addPersonHistory = vi.fn();
    const updatePersonHistory = vi.fn();

    mockUseSchedulingData.mockReturnValue({
      dateData: {
        range: {
          startDate: new Date('2026-01-01T12:00:00.000Z'),
          endDate: new Date('2026-01-01T12:00:00.000Z'),
        },
        items: [{ id: '01', description: 'Jan 1' }],
        groups: [{ id: 'ALL_DATES', members: ['01'], description: '' }],
      },
      peopleData: {
        items: [{ id: 'Person 1', description: '', history: ['D', 'N'] }],
        groups: [{ id: 'ALL_PEOPLE', members: ['Person 1'], description: '' }],
        history: [],
      },
      shiftTypeData: {
        items: [
          { id: 'D', description: 'Day' },
          { id: 'N', description: 'Night' },
        ],
        groups: [{ id: 'ALL_SHIFT_TYPES', members: ['D', 'N'], description: '' }],
      },
      getPreferencesByType: vi.fn(() => []),
      updatePreferencesByType,
      addPersonHistory,
      updatePersonHistory,
      reorderItems,
    });

    const { container } = renderShiftRequestsPage();

    await user.click(screen.getByRole('button', { name: /quick add preference/i }));
    const firstHistoryCell = container.querySelector('td[title="Click or drag to set history position H-2 to clear"]') as HTMLTableCellElement;
    const secondHistoryCell = container.querySelector('td[title="Click or drag to set history position H-1 to clear"]') as HTMLTableCellElement;

    fireEvent.mouseDown(firstHistoryCell, { button: 0 });
    fireEvent.mouseEnter(secondHistoryCell);
    fireEvent.mouseUp(secondHistoryCell, { button: 0 });

    expect(addPersonHistory).not.toHaveBeenCalled();
    expect(updatePersonHistory).toHaveBeenCalledTimes(1);
    expect(updatePersonHistory).toHaveBeenCalledWith('Person 1', 1, undefined, { replaceLatestHistoryEntry: false });
  });

  it('maps clear-mode drag columns through leading padding for shorter history rows', async () => {
    const user = userEvent.setup();
    const updatePersonHistory = vi.fn();

    mockUseSchedulingData.mockReturnValue({
      dateData: {
        range: {
          startDate: new Date('2026-01-01T12:00:00.000Z'),
          endDate: new Date('2026-01-01T12:00:00.000Z'),
        },
        items: [{ id: '01', description: 'Jan 1' }],
        groups: [{ id: 'ALL_DATES', members: ['01'], description: '' }],
      },
      peopleData: {
        items: [
          { id: 'Person 1', description: '', history: ['D', 'N', 'E'] },
          { id: 'Person 2', description: '', history: ['D'] },
        ],
        groups: [{ id: 'ALL_PEOPLE', members: ['Person 1', 'Person 2'], description: '' }],
        history: [],
      },
      shiftTypeData: {
        items: [
          { id: 'D', description: 'Day' },
          { id: 'N', description: 'Night' },
          { id: 'E', description: 'Evening' },
        ],
        groups: [{ id: 'ALL_SHIFT_TYPES', members: ['D', 'N', 'E'], description: '' }],
      },
      getPreferencesByType: vi.fn(() => []),
      updatePreferencesByType,
      addPersonHistory: vi.fn(),
      updatePersonHistory,
      reorderItems,
    });

    renderShiftRequestsPage();

    await user.click(screen.getByRole('button', { name: /quick add preference/i }));
    const shorterHistoryRow = screen.getByRole('row', { name: /2\. Person 2/ });
    const paddedClickableCell = within(shorterHistoryRow).getByTitle('Click or drag to set history position H-2 to clear');
    const existingHistoryCell = within(shorterHistoryRow).getByTitle('Click or drag to set history position H-1 to clear');

    fireEvent.mouseDown(paddedClickableCell, { button: 0 });
    fireEvent.mouseEnter(existingHistoryCell);
    fireEvent.mouseUp(existingHistoryCell, { button: 0 });

    expect(updatePersonHistory).toHaveBeenCalledTimes(1);
    expect(updatePersonHistory).toHaveBeenCalledWith('Person 2', 0, undefined, { replaceLatestHistoryEntry: false });
  });

  it('parses whitespace-padded CSV values for shift requests', async () => {
    const user = userEvent.setup();
    fileContentsByName.set('shift-requests.csv', '  Person 1  ,  D  \n');

    renderShiftRequestsPage();

    await user.click(screen.getByRole('button', { name: /quick add preference/i }));
    fireEvent.change(
      screen.getByPlaceholderText('Enter weight (positive for preference, negative for avoidance, or Infinity/-Infinity)'),
      { target: { value: '2' } },
    );
    fireEvent.click(screen.getByRole('button', { name: /upload shift requests/i }));

    expect(updatePreferencesByType).toHaveBeenCalledWith(
      'shift request',
      [
        {
          type: 'shift request',
          person: ['Person 1'],
          date: ['01'],
          shiftType: ['D'],
          weight: 2,
        },
      ],
      undefined,
    );
  });

  it('accepts BOM-prefixed person IDs after CSV trimming', async () => {
    const user = userEvent.setup();
    fileContentsByName.set('shift-requests.csv', '\uFEFFPerson 1,D\n');

    renderShiftRequestsPage();

    await user.click(screen.getByRole('button', { name: /quick add preference/i }));
    fireEvent.change(
      screen.getByPlaceholderText('Enter weight (positive for preference, negative for avoidance, or Infinity/-Infinity)'),
      { target: { value: '2' } },
    );
    fireEvent.click(screen.getByRole('button', { name: /upload shift requests/i }));

    expect(updatePreferencesByType).toHaveBeenCalledWith(
      'shift request',
      [
        {
          type: 'shift request',
          person: ['Person 1'],
          date: ['01'],
          shiftType: ['D'],
          weight: 2,
        },
      ],
      undefined,
    );
  });

  it('rejects unknown shift type IDs in shift-requests CSV', async () => {
    const user = userEvent.setup();
    (alert as unknown as ReturnType<typeof vi.fn>).mockClear();
    fileContentsByName.set('shift-requests.csv', 'Person 1,X\n');

    renderShiftRequestsPage();

    await user.click(screen.getByRole('button', { name: /quick add preference/i }));
    fireEvent.change(
      screen.getByPlaceholderText('Enter weight (positive for preference, negative for avoidance, or Infinity/-Infinity)'),
      { target: { value: '2' } },
    );
    fireEvent.click(screen.getByRole('button', { name: /upload shift requests/i }));

    expect(alert).toHaveBeenCalledWith(
      expect.stringContaining('CSV validation failed: Invalid shift type "X" at row 1, column 2'),
    );
    expect(updatePreferencesByType).not.toHaveBeenCalled();
  });

  it('shows validation error for invalid repetition counts in people-history CSV', async () => {
    const user = userEvent.setup();
    (alert as unknown as ReturnType<typeof vi.fn>).mockClear();
    fileContentsByName.set('people-history.csv', 'Person 1,D,-1\n');

    renderShiftRequestsPage();

    await user.click(screen.getByRole('button', { name: /quick add preference/i }));
    fireEvent.click(screen.getByRole('button', { name: /upload people history \(shorthand\)/i }));

    expect(alert).toHaveBeenCalledWith(
      expect.stringContaining("CSV validation failed: Invalid repetition count '-1' for person 'Person 1' at row 1"),
    );
    expect(reorderItems).not.toHaveBeenCalled();
  });

  it('shows validation error for unknown shift types in people-history CSV', async () => {
    const user = userEvent.setup();
    (alert as unknown as ReturnType<typeof vi.fn>).mockClear();
    fileContentsByName.set('people-history.csv', 'Person 1,X,1\n');

    renderShiftRequestsPage();

    await user.click(screen.getByRole('button', { name: /quick add preference/i }));
    fireEvent.click(screen.getByRole('button', { name: /upload people history \(shorthand\)/i }));

    expect(alert).toHaveBeenCalledWith(
      expect.stringContaining('CSV validation failed: Invalid shift type "X" at row 1. Valid shift types: D'),
    );
    expect(reorderItems).not.toHaveBeenCalled();
  });

  it('accepts empty shift types in people-history CSV as zero-history rows', async () => {
    const user = userEvent.setup();
    (alert as unknown as ReturnType<typeof vi.fn>).mockClear();
    fileContentsByName.set('people-history.csv', 'Person 1,,0\n');

    renderShiftRequestsPage();

    await user.click(screen.getByRole('button', { name: /quick add preference/i }));
    fireEvent.click(screen.getByRole('button', { name: /upload people history \(shorthand\)/i }));

    expect(reorderItems).toHaveBeenCalledWith(
      'people',
      expect.objectContaining({
        items: [expect.objectContaining({ id: 'Person 1', history: [] })],
      }),
      [expect.objectContaining({ id: 'Person 1', history: [] })],
    );
    expect(alert).toHaveBeenCalledWith('Successfully processed 1 shift type entries from people history CSV!');
  });

  it('shows exact row-count mismatch errors for multi-person people-history CSV uploads', async () => {
    const user = userEvent.setup();
    (alert as unknown as ReturnType<typeof vi.fn>).mockClear();

    mockUseSchedulingData.mockReturnValue({
      dateData: {
        range: {
          startDate: new Date('2026-01-01T12:00:00.000Z'),
          endDate: new Date('2026-01-01T12:00:00.000Z'),
        },
        items: [{ id: '01', description: 'Jan 1' }],
        groups: [{ id: 'ALL_DATES', members: ['01'], description: '' }],
      },
      peopleData: {
        items: [
          { id: 'Person 1', description: '', history: [] },
          { id: 'Person 2', description: '', history: [] },
        ],
        groups: [{ id: 'ALL_PEOPLE', members: ['Person 1', 'Person 2'], description: '' }],
        history: [],
      },
      shiftTypeData: {
        items: [{ id: 'D', description: 'Day' }],
        groups: [{ id: 'ALL_SHIFT_TYPES', members: ['D'], description: '' }],
      },
      getPreferencesByType: vi.fn(() => []),
      updatePreferencesByType,
      addPersonHistory: vi.fn(),
      updatePersonHistory: vi.fn(),
      reorderItems,
    });

    fileContentsByName.set('people-history.csv', 'Person 1,D,1\n');

    renderShiftRequestsPage();

    await user.click(screen.getByRole('button', { name: /quick add preference/i }));
    fireEvent.click(screen.getByRole('button', { name: /upload people history \(shorthand\)/i }));

    expect(alert).toHaveBeenCalledWith(
      'CSV validation failed: CSV should have 2 rows (one per person), but has 1 rows.',
    );
    expect(reorderItems).not.toHaveBeenCalled();
  });
});
