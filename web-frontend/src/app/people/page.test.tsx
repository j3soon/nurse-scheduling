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
import PeoplePage from '@/app/people/page';

const mockUseSchedulingData = vi.hoisted(() => vi.fn());
const fileContentsByName = new Map<string, string>();

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

vi.mock('@/components/ItemGroupEditorPage', () => ({
  __esModule: true,
  default: ({ title, itemTableHeaderAction }: { title: string; itemTableHeaderAction: React.ReactNode }) => (
    <div>
      <h1>{title}</h1>
      {itemTableHeaderAction}
    </div>
  ),
}));

vi.mock('@/components/UploadButton', () => ({
  __esModule: true,
  default: ({ onFileUpload, buttonText }: { onFileUpload: (file: File) => void; buttonText: string }) => (
    <button onClick={() => onFileUpload(new File(['ignored'], 'people.txt', { type: 'text/plain' }))}>
      {buttonText}
    </button>
  ),
}));

describe('PeoplePage upload parsing', () => {
  const baseMockData = {
    addItem: vi.fn(),
    addGroup: vi.fn(),
    updateItem: vi.fn(),
    updateGroup: vi.fn(),
    deleteItem: vi.fn(),
    deleteGroup: vi.fn(),
    removeItemFromGroup: vi.fn(),
    reorderGroups: vi.fn(),
  };

  it('alerts and blocks updates when uploaded people list has duplicates', () => {
    const reorderItems = vi.fn();

    mockUseSchedulingData.mockReturnValue({
      peopleData: {
        items: [{ id: 'Alice', description: '', history: [] }],
        groups: [],
        history: [],
      },
      addItem: vi.fn(),
      addGroup: vi.fn(),
      updateItem: vi.fn(),
      updateGroup: vi.fn(),
      deleteItem: vi.fn(),
      deleteGroup: vi.fn(),
      removeItemFromGroup: vi.fn(),
      reorderItems,
      reorderGroups: vi.fn(),
    });

    fileContentsByName.set('people.txt', 'Alice\nAlice\nBob\n');
    vi.stubGlobal('FileReader', MockFileReader as unknown as typeof FileReader);
    const alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => undefined);

    render(<PeoplePage />);

    fireEvent.click(screen.getByRole('button', { name: /upload people/i }));

    expect(alertSpy).toHaveBeenCalledWith(
      'Duplicate person name "Alice" found in the uploaded list. Please remove duplicates.',
    );
    expect(reorderItems).not.toHaveBeenCalled();
  });

  it('reorders and adds people on valid upload with success summary', () => {
    const reorderItems = vi.fn();

    mockUseSchedulingData.mockReturnValue({
      peopleData: {
        items: [{ id: 'Alice', description: '', history: [] }],
        groups: [],
        history: [],
      },
      addItem: vi.fn(),
      addGroup: vi.fn(),
      updateItem: vi.fn(),
      updateGroup: vi.fn(),
      deleteItem: vi.fn(),
      deleteGroup: vi.fn(),
      removeItemFromGroup: vi.fn(),
      reorderItems,
      reorderGroups: vi.fn(),
    });

    fileContentsByName.set('people.txt', 'Alice\nBob\n');
    vi.stubGlobal('FileReader', MockFileReader as unknown as typeof FileReader);
    const alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => undefined);

    render(<PeoplePage />);

    fireEvent.click(screen.getByRole('button', { name: /upload people/i }));

    expect(reorderItems).toHaveBeenCalledTimes(1);
    expect(reorderItems).toHaveBeenCalledWith(
      'people',
      expect.objectContaining({
        items: expect.arrayContaining([
          expect.objectContaining({ id: 'Alice' }),
          expect.objectContaining({ id: 'Bob' }),
        ]),
      }),
      expect.arrayContaining([
        expect.objectContaining({ id: 'Alice' }),
        expect.objectContaining({ id: 'Bob' }),
      ]),
    );
    expect(alertSpy).toHaveBeenCalledWith(
      'Successfully uploaded 2 people: 1 existing people reordered, 1 new people added, 0 existing people moved to end.',
    );
  });

  it('treats trimmed duplicates as duplicates and blocks updates', () => {
    const reorderItems = vi.fn();

    mockUseSchedulingData.mockReturnValue({
      peopleData: {
        items: [{ id: 'Alice', description: '', history: [] }],
        groups: [],
        history: [],
      },
      reorderItems,
      ...baseMockData,
    });

    fileContentsByName.set('people.txt', ' Alice \nAlice\n');
    vi.stubGlobal('FileReader', MockFileReader as unknown as typeof FileReader);
    const alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => undefined);

    render(<PeoplePage />);
    fireEvent.click(screen.getByRole('button', { name: /upload people/i }));

    expect(alertSpy).toHaveBeenCalledWith(
      'Duplicate person name "Alice" found in the uploaded list. Please remove duplicates.',
    );
    expect(reorderItems).not.toHaveBeenCalled();
  });

  it('ignores comments and blank lines when uploading people', () => {
    const reorderItems = vi.fn();

    mockUseSchedulingData.mockReturnValue({
      peopleData: {
        items: [{ id: 'Alice', description: '', history: [] }],
        groups: [],
        history: [],
      },
      reorderItems,
      ...baseMockData,
    });

    fileContentsByName.set('people.txt', '# comment\n\n Alice \n# another\nBob\n');
    vi.stubGlobal('FileReader', MockFileReader as unknown as typeof FileReader);
    const alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => undefined);

    render(<PeoplePage />);
    fireEvent.click(screen.getByRole('button', { name: /upload people/i }));

    expect(reorderItems).toHaveBeenCalledTimes(1);
    expect(alertSpy).toHaveBeenCalledWith(
      'Successfully uploaded 2 people: 1 existing people reordered, 1 new people added, 0 existing people moved to end.',
    );
  });

  it('alerts when uploaded people file has no usable names', () => {
    const reorderItems = vi.fn();

    mockUseSchedulingData.mockReturnValue({
      peopleData: {
        items: [],
        groups: [],
        history: [],
      },
      reorderItems,
      ...baseMockData,
    });

    fileContentsByName.set('people.txt', '\n# only comments\n   \n');
    vi.stubGlobal('FileReader', MockFileReader as unknown as typeof FileReader);
    const alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => undefined);

    render(<PeoplePage />);
    fireEvent.click(screen.getByRole('button', { name: /upload people/i }));

    expect(alertSpy).toHaveBeenCalledWith('No people names found in the uploaded file.');
    expect(reorderItems).not.toHaveBeenCalled();
  });

  it('alerts when the uploaded file resolves with no readable content', () => {
    const reorderItems = vi.fn();

    mockUseSchedulingData.mockReturnValue({
      peopleData: {
        items: [],
        groups: [],
        history: [],
      },
      reorderItems,
      ...baseMockData,
    });

    fileContentsByName.set('people.txt', '');
    vi.stubGlobal('FileReader', MockFileReader as unknown as typeof FileReader);
    const alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => undefined);

    render(<PeoplePage />);
    fireEvent.click(screen.getByRole('button', { name: /upload people/i }));

    expect(alertSpy).toHaveBeenCalledWith('No content found in the uploaded file.');
    expect(reorderItems).not.toHaveBeenCalled();
  });

  it('warns and blocks uploads that exceed the maximum people count', () => {
    const reorderItems = vi.fn();

    mockUseSchedulingData.mockReturnValue({
      peopleData: {
        items: [],
        groups: [],
        history: [],
      },
      reorderItems,
      ...baseMockData,
    });

    fileContentsByName.set(
      'people.txt',
      Array.from({ length: 1005 }, (_, index) => `Person ${index + 1}`).join('\n'),
    );
    vi.stubGlobal('FileReader', MockFileReader as unknown as typeof FileReader);
    const alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => undefined);

    render(<PeoplePage />);
    fireEvent.click(screen.getByRole('button', { name: /upload people/i }));

    expect(reorderItems).not.toHaveBeenCalled();
    expect(alertSpy).toHaveBeenCalledWith(
      'Uploaded file contains 1005 people, which exceeds the maximum of 1000. Please split the file and upload fewer names at a time.',
    );
  });

  it('preserves existing descriptions and history when reordering known people via upload', () => {
    const reorderItems = vi.fn();

    mockUseSchedulingData.mockReturnValue({
      peopleData: {
        items: [
          { id: 'Alice', description: 'Primary nurse', history: ['D'] },
          { id: 'Bob', description: 'Night shift expert', history: ['N', 'N'] },
        ],
        groups: [],
        history: [],
      },
      reorderItems,
      ...baseMockData,
    });

    fileContentsByName.set('people.txt', 'Bob\nAlice\nCharlie\n');
    vi.stubGlobal('FileReader', MockFileReader as unknown as typeof FileReader);
    const alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => undefined);

    render(<PeoplePage />);
    fireEvent.click(screen.getByRole('button', { name: /upload people/i }));

    expect(reorderItems).toHaveBeenCalledWith(
      'people',
      expect.objectContaining({
        items: [
          { id: 'Bob', description: 'Night shift expert', history: ['N', 'N'] },
          { id: 'Alice', description: 'Primary nurse', history: ['D'] },
          { id: 'Charlie', description: '', history: [] },
        ],
      }),
      [
        { id: 'Bob', description: 'Night shift expert', history: ['N', 'N'] },
        { id: 'Alice', description: 'Primary nurse', history: ['D'] },
        { id: 'Charlie', description: '', history: [] },
      ],
    );
    expect(alertSpy).toHaveBeenCalledWith(
      'Successfully uploaded 3 people: 2 existing people reordered, 1 new people added, 0 existing people moved to end.',
    );
  });

  it('recovers from duplicate-name upload errors and still preserves metadata on the next valid upload', () => {
    const reorderItems = vi.fn();

    mockUseSchedulingData.mockReturnValue({
      peopleData: {
        items: [
          { id: 'Alice', description: 'Primary nurse', history: ['D'] },
          { id: 'Bob', description: 'Night shift expert', history: ['N', 'N'] },
        ],
        groups: [],
        history: [],
      },
      reorderItems,
      ...baseMockData,
    });

    vi.stubGlobal('FileReader', MockFileReader as unknown as typeof FileReader);
    const alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => undefined);

    render(<PeoplePage />);

    fileContentsByName.set('people.txt', 'Alice\nAlice\nBob\n');
    fireEvent.click(screen.getByRole('button', { name: /upload people/i }));

    expect(alertSpy).toHaveBeenCalledWith(
      'Duplicate person name "Alice" found in the uploaded list. Please remove duplicates.',
    );
    expect(reorderItems).not.toHaveBeenCalled();

    fileContentsByName.set('people.txt', 'Bob\nAlice\nCharlie\n');
    fireEvent.click(screen.getByRole('button', { name: /upload people/i }));

    expect(reorderItems).toHaveBeenCalledWith(
      'people',
      expect.objectContaining({
        items: [
          { id: 'Bob', description: 'Night shift expert', history: ['N', 'N'] },
          { id: 'Alice', description: 'Primary nurse', history: ['D'] },
          { id: 'Charlie', description: '', history: [] },
        ],
      }),
      [
        { id: 'Bob', description: 'Night shift expert', history: ['N', 'N'] },
        { id: 'Alice', description: 'Primary nurse', history: ['D'] },
        { id: 'Charlie', description: '', history: [] },
      ],
    );
  });
});
