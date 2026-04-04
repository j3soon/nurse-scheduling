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
import UploadButton from '@/components/UploadButton';

describe('UploadButton', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('uploads a valid selected file', async () => {
    const user = userEvent.setup();
    const onFileUpload = vi.fn();

    const { container } = render(
      <UploadButton
        onFileUpload={onFileUpload}
        acceptedFileTypes={['.yaml', '.yml']}
        buttonText="Upload"
        tooltipText="Upload YAML"
      />,
    );

    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(['name: test'], 'schedule.yaml', { type: 'text/yaml' });

    await user.upload(input, file);

    expect(onFileUpload).toHaveBeenCalledTimes(1);
    expect(onFileUpload).toHaveBeenCalledWith(expect.objectContaining({ name: 'schedule.yaml' }));
  });

  it('rejects invalid file extension from selected file and alerts', () => {
    const onFileUpload = vi.fn();
    const alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => undefined);

    const { container } = render(
      <UploadButton
        onFileUpload={onFileUpload}
        acceptedFileTypes={['.yaml']}
        buttonText="Upload"
        tooltipText="Upload YAML"
      />,
    );

    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(['x'], 'schedule.csv', { type: 'text/csv' });

    fireEvent.change(input, {
      target: { files: [file] },
    });

    expect(onFileUpload).not.toHaveBeenCalled();
    expect(alertSpy).toHaveBeenCalledWith('Please upload a file with one of these extensions: .yaml');
  });

  it('handles drag-over and drop of a valid file', () => {
    const onFileUpload = vi.fn();

    render(
      <UploadButton
        onFileUpload={onFileUpload}
        acceptedFileTypes={['.yaml']}
        buttonText="Upload"
        tooltipText="Upload YAML"
      />,
    );

    const button = screen.getByRole('button', { name: /upload/i });

    fireEvent.dragOver(button, {
      dataTransfer: { files: [] },
    });
    expect(button.className).toContain('border-dashed');

    const file = new File(['name: test'], 'drop.yaml', { type: 'text/yaml' });
    fireEvent.drop(button, {
      dataTransfer: { files: [file] },
    });

    expect(onFileUpload).toHaveBeenCalledTimes(1);
    expect(onFileUpload).toHaveBeenCalledWith(expect.objectContaining({ name: 'drop.yaml' }));
  });

  it('alerts when drop has no files', () => {
    const onFileUpload = vi.fn();
    const alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => undefined);

    render(
      <UploadButton
        onFileUpload={onFileUpload}
        acceptedFileTypes={['.yaml']}
        buttonText="Upload"
        tooltipText="Upload YAML"
      />,
    );

    const button = screen.getByRole('button', { name: /upload/i });

    fireEvent.drop(button, {
      dataTransfer: { files: [] },
    });

    expect(onFileUpload).not.toHaveBeenCalled();
    expect(alertSpy).toHaveBeenCalledWith('No file was dropped.');
  });

  it('does not process dropped files when disabled', () => {
    const onFileUpload = vi.fn();

    render(
      <UploadButton
        onFileUpload={onFileUpload}
        acceptedFileTypes={['.yaml']}
        buttonText="Upload"
        tooltipText="Upload YAML"
        disabled={true}
      />,
    );

    const button = screen.getByRole('button', { name: /upload/i });
    const file = new File(['name: test'], 'drop.yaml', { type: 'text/yaml' });

    fireEvent.drop(button, {
      dataTransfer: { files: [file] },
    });

    expect(onFileUpload).not.toHaveBeenCalled();
  });

  it('rejects invalid file extension from drop and alerts', () => {
    const onFileUpload = vi.fn();
    const alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => undefined);

    render(
      <UploadButton
        onFileUpload={onFileUpload}
        acceptedFileTypes={['.yaml']}
        buttonText="Upload"
        tooltipText="Upload YAML"
      />,
    );

    const button = screen.getByRole('button', { name: /upload/i });
    const file = new File(['x'], 'drop.csv', { type: 'text/csv' });

    fireEvent.drop(button, {
      dataTransfer: { files: [file] },
    });

    expect(onFileUpload).not.toHaveBeenCalled();
    expect(alertSpy).toHaveBeenCalledWith('Please upload a file with one of these extensions: .yaml');
  });

  it('applies drag-over style while removing hover/focus custom classes', () => {
    const onFileUpload = vi.fn();

    render(
      <UploadButton
        onFileUpload={onFileUpload}
        acceptedFileTypes={['.yaml']}
        buttonText="Upload"
        tooltipText="Upload YAML"
        className="hover:bg-red-600 focus:ring-red-600 bg-green-600 text-white"
      />,
    );

    const button = screen.getByRole('button', { name: /upload/i });
    fireEvent.dragOver(button, {
      dataTransfer: { files: [] },
    });

    expect(button.className).toContain('border-dashed');
    expect(button.className).toContain('bg-green-600');
    expect(button.className).not.toContain('hover:bg-red-600');
    expect(button.className).not.toContain('focus:ring-red-600');
  });

  it('opens the hidden file input when upload button is clicked', async () => {
    const user = userEvent.setup();

    const { container } = render(
      <UploadButton
        onFileUpload={vi.fn()}
        acceptedFileTypes={['.yaml']}
        buttonText="Upload"
        tooltipText="Upload YAML"
      />,
    );

    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    const clickSpy = vi.spyOn(input, 'click');

    await user.click(screen.getByRole('button', { name: /upload/i }));

    expect(clickSpy).toHaveBeenCalledTimes(1);
  });

  it('clears drag-over visual state on drag leave', () => {
    render(
      <UploadButton
        onFileUpload={vi.fn()}
        acceptedFileTypes={['.yaml']}
        buttonText="Upload"
        tooltipText="Upload YAML"
      />,
    );

    const button = screen.getByRole('button', { name: /upload/i });
    fireEvent.dragOver(button, { dataTransfer: { files: [] } });
    expect(button.className).toContain('border-dashed');

    fireEvent.dragLeave(button, { dataTransfer: { files: [] } });
    expect(button.className).not.toContain('border-dashed');
  });

  it('uses the first dropped file when multiple files are dropped', () => {
    const onFileUpload = vi.fn();

    render(
      <UploadButton
        onFileUpload={onFileUpload}
        acceptedFileTypes={['.yaml']}
        buttonText="Upload"
        tooltipText="Upload YAML"
      />,
    );

    const firstFile = new File(['first'], 'first.yaml', { type: 'text/yaml' });
    const secondFile = new File(['second'], 'second.yaml', { type: 'text/yaml' });
    fireEvent.drop(screen.getByRole('button', { name: /upload/i }), {
      dataTransfer: { files: [firstFile, secondFile] },
    });

    expect(onFileUpload).toHaveBeenCalledTimes(1);
    expect(onFileUpload).toHaveBeenCalledWith(expect.objectContaining({ name: 'first.yaml' }));
  });

  it('accepts uppercase file extensions via case-insensitive validation', () => {
    const onFileUpload = vi.fn();

    const { container } = render(
      <UploadButton
        onFileUpload={onFileUpload}
        acceptedFileTypes={['.yaml']}
        buttonText="Upload"
        tooltipText="Upload YAML"
      />,
    );

    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(['name: test'], 'SCHEDULE.YAML', { type: 'text/yaml' });

    fireEvent.change(input, {
      target: { files: [file] },
    });

    expect(onFileUpload).toHaveBeenCalledTimes(1);
    expect(onFileUpload).toHaveBeenCalledWith(expect.objectContaining({ name: 'SCHEDULE.YAML' }));
  });

  it('resets file input value after invalid selection so the same file can be selected again', () => {
    const onFileUpload = vi.fn();
    vi.spyOn(window, 'alert').mockImplementation(() => undefined);

    const { container } = render(
      <UploadButton
        onFileUpload={onFileUpload}
        acceptedFileTypes={['.yaml']}
        buttonText="Upload"
        tooltipText="Upload YAML"
      />,
    );

    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    const badFile = new File(['bad'], 'schedule.csv', { type: 'text/csv' });

    Object.defineProperty(input, 'value', { configurable: true, writable: true, value: 'C:\\fakepath\\schedule.csv' });
    fireEvent.change(input, { target: { files: [badFile] } });
    expect(input.value).toBe('');

    Object.defineProperty(input, 'value', { configurable: true, writable: true, value: 'C:\\fakepath\\schedule.csv' });
    fireEvent.change(input, { target: { files: [badFile] } });
    expect(input.value).toBe('');
    expect(onFileUpload).not.toHaveBeenCalled();
  });

  it('uses a comma-joined accept attribute and matching alert message for multiple extensions', () => {
    const onFileUpload = vi.fn();
    const alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => undefined);

    const { container } = render(
      <UploadButton
        onFileUpload={onFileUpload}
        acceptedFileTypes={['.yaml', '.yml', '.csv']}
        buttonText="Upload"
        tooltipText="Upload data"
      />,
    );

    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    expect(input.accept).toBe('.yaml,.yml,.csv');

    fireEvent.change(input, {
      target: { files: [new File(['bad'], 'schedule.txt', { type: 'text/plain' })] },
    });

    expect(onFileUpload).not.toHaveBeenCalled();
    expect(alertSpy).toHaveBeenCalledWith(
      'Please upload a file with one of these extensions: .yaml, .yml, .csv',
    );
  });

  it('rejects filenames without a usable extension', () => {
    const onFileUpload = vi.fn();
    const alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => undefined);

    const { container } = render(
      <UploadButton
        onFileUpload={onFileUpload}
        acceptedFileTypes={['.yaml']}
        buttonText="Upload"
        tooltipText="Upload YAML"
      />,
    );

    const input = container.querySelector('input[type="file"]') as HTMLInputElement;

    fireEvent.change(input, { target: { files: [new File(['x'], 'schedule', { type: 'text/plain' })] } });
    fireEvent.change(input, { target: { files: [new File(['x'], 'schedule.', { type: 'text/plain' })] } });
    fireEvent.change(input, { target: { files: [new File(['x'], '.env', { type: 'text/plain' })] } });

    expect(onFileUpload).not.toHaveBeenCalled();
    expect(alertSpy).toHaveBeenCalledTimes(3);
  });

  it('does not trigger hidden input click when disabled', async () => {
    const user = userEvent.setup();

    const { container } = render(
      <UploadButton
        onFileUpload={vi.fn()}
        acceptedFileTypes={['.yaml']}
        buttonText="Upload"
        tooltipText="Upload YAML"
        disabled={true}
      />,
    );

    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    const clickSpy = vi.spyOn(input, 'click');

    await user.click(screen.getByRole('button', { name: /upload/i }));

    expect(clickSpy).not.toHaveBeenCalled();
  });

  it('does not apply drag-over styling while disabled', () => {
    render(
      <UploadButton
        onFileUpload={vi.fn()}
        acceptedFileTypes={['.yaml']}
        buttonText="Upload"
        tooltipText="Upload YAML"
        disabled={true}
      />,
    );

    const button = screen.getByRole('button', { name: /upload/i });
    fireEvent.dragOver(button, { dataTransfer: { files: [] } });

    expect(button.className).not.toContain('border-dashed');
  });

  it('accepts a valid file after an invalid selection using the same input element', () => {
    const onFileUpload = vi.fn();
    vi.spyOn(window, 'alert').mockImplementation(() => undefined);

    const { container } = render(
      <UploadButton
        onFileUpload={onFileUpload}
        acceptedFileTypes={['.yaml']}
        buttonText="Upload"
        tooltipText="Upload YAML"
      />,
    );

    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    const badFile = new File(['bad'], 'schedule.csv', { type: 'text/csv' });
    const goodFile = new File(['good'], 'schedule.yaml', { type: 'text/yaml' });

    Object.defineProperty(input, 'value', { configurable: true, writable: true, value: 'C:\\fakepath\\schedule.csv' });
    fireEvent.change(input, { target: { files: [badFile] } });
    expect(input.value).toBe('');

    Object.defineProperty(input, 'value', { configurable: true, writable: true, value: 'C:\\fakepath\\schedule.yaml' });
    fireEvent.change(input, { target: { files: [goodFile] } });

    expect(onFileUpload).toHaveBeenCalledTimes(1);
    expect(onFileUpload).toHaveBeenCalledWith(expect.objectContaining({ name: 'schedule.yaml' }));
    expect(input.value).toBe('');
  });

  it('allows selecting the same valid filename twice by clearing the input after each upload', () => {
    const onFileUpload = vi.fn();

    const { container } = render(
      <UploadButton
        onFileUpload={onFileUpload}
        acceptedFileTypes={['.yaml']}
        buttonText="Upload"
        tooltipText="Upload YAML"
      />,
    );

    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(['good'], 'schedule.yaml', { type: 'text/yaml' });

    Object.defineProperty(input, 'value', { configurable: true, writable: true, value: 'C:\\fakepath\\schedule.yaml' });
    fireEvent.change(input, { target: { files: [file] } });
    expect(input.value).toBe('');

    Object.defineProperty(input, 'value', { configurable: true, writable: true, value: 'C:\\fakepath\\schedule.yaml' });
    fireEvent.change(input, { target: { files: [file] } });

    expect(onFileUpload).toHaveBeenCalledTimes(2);
    expect(onFileUpload).toHaveBeenNthCalledWith(1, expect.objectContaining({ name: 'schedule.yaml' }));
    expect(onFileUpload).toHaveBeenNthCalledWith(2, expect.objectContaining({ name: 'schedule.yaml' }));
    expect(input.value).toBe('');
  });

  it('accepts a valid dropped file after a prior invalid dropped file', () => {
    const onFileUpload = vi.fn();
    const alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => undefined);

    render(
      <UploadButton
        onFileUpload={onFileUpload}
        acceptedFileTypes={['.yaml']}
        buttonText="Upload"
        tooltipText="Upload YAML"
      />,
    );

    const button = screen.getByRole('button', { name: /upload/i });
    const badFile = new File(['bad'], 'bad.csv', { type: 'text/csv' });
    const goodFile = new File(['good'], 'good.yaml', { type: 'text/yaml' });

    fireEvent.drop(button, { dataTransfer: { files: [badFile] } });
    fireEvent.drop(button, { dataTransfer: { files: [goodFile] } });

    expect(alertSpy).toHaveBeenCalledWith('Please upload a file with one of these extensions: .yaml');
    expect(onFileUpload).toHaveBeenCalledTimes(1);
    expect(onFileUpload).toHaveBeenCalledWith(expect.objectContaining({ name: 'good.yaml' }));
  });

  it('stops opening the hidden input after rerendering from enabled to disabled', async () => {
    const user = userEvent.setup();
    const { container, rerender } = render(
      <UploadButton
        onFileUpload={vi.fn()}
        acceptedFileTypes={['.yaml']}
        buttonText="Upload"
        tooltipText="Upload YAML"
      />,
    );

    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    const clickSpy = vi.spyOn(input, 'click');

    await user.click(screen.getByRole('button', { name: /upload/i }));
    expect(clickSpy).toHaveBeenCalledTimes(1);

    rerender(
      <UploadButton
        onFileUpload={vi.fn()}
        acceptedFileTypes={['.yaml']}
        buttonText="Upload"
        tooltipText="Upload YAML"
        disabled={true}
      />,
    );

    fireEvent.dragOver(screen.getByRole('button', { name: /upload/i }), { dataTransfer: { files: [] } });
    await user.click(screen.getByRole('button', { name: /upload/i }));

    expect(clickSpy).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('button', { name: /upload/i }).className).not.toContain('border-dashed');
  });
});
