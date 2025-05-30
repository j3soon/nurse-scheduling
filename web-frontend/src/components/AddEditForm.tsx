'use client';

import { FormInput } from '@/components/FormInput';
import { CheckboxSelector } from '@/components/CheckboxSelector';
import { Item, Group } from '@/types/management';
import { Mode } from '@/constants/modes';

interface AddEditFormProps<T extends Item, G extends Group> {
  mode: Mode.ADDING | Mode.EDITING;
  draft: {
    id: string;
    description: string;
    groups: string[];
    members: string[];
    isItem: boolean;
  };
  items: T[];
  groups: G[];
  itemLabel: string;
  itemLabelPlural: string;
  groupLabel: string;
  groupLabelPlural: string;
  error: string;
  onIdChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  onDescriptionChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  onKeyDown: (e: React.KeyboardEvent<HTMLInputElement>) => void;
  onMemberToggle: (id: string) => void;
  onSave: () => void;
  onCancel: () => void;
}

export function AddEditForm<T extends Item, G extends Group>({
  mode,
  draft,
  items,
  groups,
  itemLabel,
  itemLabelPlural,
  groupLabel,
  groupLabelPlural,
  error,
  onIdChange,
  onDescriptionChange,
  onKeyDown,
  onMemberToggle,
  onSave,
  onCancel,
}: AddEditFormProps<T, G>) {
  const isItem = draft.isItem;
  const title = `${mode === Mode.ADDING ? 'Add New' : 'Edit'} ${isItem ? itemLabel : groupLabel}`;
  const placeholder = `Enter ${isItem ? itemLabel.toLowerCase() : groupLabel.toLowerCase()} ID`;

  return (
    <div className="mb-6 bg-white shadow-md rounded-lg overflow-hidden">
      <div className="px-6 py-4">
        <h2 className="text-lg font-semibold mb-4 text-gray-800">{title}</h2>
        <FormInput
          itemValue={draft.id}
          itemPlaceholder={placeholder}
          onItemChange={onIdChange}
          descriptionValue={draft.description}
          descriptionPlaceholder={`Enter ${isItem ? itemLabel.toLowerCase() : groupLabel.toLowerCase()} description (optional)`}
          onDescriptionChange={onDescriptionChange}
          onKeyDown={onKeyDown}
          error={error}
          onAction={onSave}
          onCancel={onCancel}
          actionText={mode === Mode.ADDING ? 'Add' : 'Update'}
        >
          <CheckboxSelector
            items={draft.isItem ? groups : items}
            selectedIds={draft.isItem ? draft.groups : draft.members}
            onToggle={onMemberToggle}
            label={draft.isItem ? groupLabelPlural : 'Members'}
          />
        </FormInput>
      </div>
    </div>
  );
}
