'use client';

import { InlineEdit } from '@/components/InlineEdit';
import { RemovableTag } from '@/components/RemovableTag';
import { TableRowActions } from '@/components/TableRowActions';
import { Item, Group } from '@/types/management';
import { Mode } from '@/constants/modes';

interface TableColumnsProps<T extends Item, G extends Group> {
  mode: Mode;
  inlineEditingId: string;
  inlineEditingField: 'id' | 'description';
  error: string;
  onInlineSave: (id: string, field: 'id' | 'description', isItem: boolean, value: string) => void;
  onInlineCancel: () => void;
  onInlineEdit: (id: string, isItem: boolean, field?: 'id' | 'description') => void;
  onEdit: (id: string) => void;
  onDelete: (id: string) => void;
  removeItemFromGroup: (itemId: string, groupId: string) => void;
}

// Common ID column component
function IdColumn<T extends Item>({
  item,
  isItem,
  mode,
  inlineEditingId,
  inlineEditingField,
  onInlineSave,
  onInlineCancel,
  onInlineEdit,
  error,
}: {
  item: T;
  isItem: boolean;
  mode: Mode;
  inlineEditingId: string;
  inlineEditingField: 'id' | 'description';
  onInlineSave: (id: string, field: 'id' | 'description', isItem: boolean, value: string) => void;
  onInlineCancel: () => void;
  onInlineEdit: (id: string, isItem: boolean, field?: 'id' | 'description') => void;
  error: string;
}) {
  return (
    <div>
      <InlineEdit
        value={item.id}
        isEditing={mode === Mode.INLINE_EDITING && inlineEditingId === item.id && inlineEditingField === 'id'}
        onSave={(value) => onInlineSave(item.id, 'id', isItem, value)}
        onCancel={onInlineCancel}
        onDoubleClick={() => onInlineEdit(item.id, isItem, 'id')}
        error={error}
      />
      <InlineEdit
        value={item.description}
        isEditing={mode === Mode.INLINE_EDITING && inlineEditingId === item.id && inlineEditingField === 'description'}
        onSave={(value) => onInlineSave(item.id, 'description', isItem, value)}
        onCancel={onInlineCancel}
        onDoubleClick={() => onInlineEdit(item.id, isItem, 'description')}
        className="text-xs text-gray-400 mt-1"
        editClassName="text-xs mt-1 w-full"
        emptyText="Add description..."
        placeholder="Enter description..."
      />
    </div>
  );
}

export function useItemTableColumns<T extends Item, G extends Group>({
  mode,
  inlineEditingId,
  inlineEditingField,
  error,
  onInlineSave,
  onInlineCancel,
  onInlineEdit,
  onEdit,
  onDelete,
  removeItemFromGroup,
  groups,
  groupLabel,
  groupLabelPlural,
}: TableColumnsProps<T, G> & { groups: G[]; groupLabel: string; groupLabelPlural: string }) {
  return [
    {
      header: 'ID',
      accessor: (item: T) => (
        <IdColumn
          item={item}
          isItem={true}
          mode={mode}
          inlineEditingId={inlineEditingId}
          inlineEditingField={inlineEditingField}
          onInlineSave={onInlineSave}
          onInlineCancel={onInlineCancel}
          onInlineEdit={onInlineEdit}
          error={error}
        />
      )
    },
    {
      header: groupLabelPlural,
      accessor: (item: T) => (
        <div className="flex flex-wrap gap-1">
          {groups
            .filter(group => group.members.includes(item.id))
            .map(group => (
              <RemovableTag
                key={group.id}
                id={group.id}
                onRemove={() => removeItemFromGroup(item.id, group.id)}
                variant="blue"
              />
            ))}
        </div>
      )
    },
    {
      header: 'Actions',
      accessor: (item: T) => (
        <TableRowActions
          onEdit={() => onEdit(item.id)}
          onDelete={() => onDelete(item.id)}
        />
      ),
      align: 'right' as const
    }
  ];
}

export function useGroupTableColumns<T extends Item, G extends Group>({
  mode,
  inlineEditingId,
  inlineEditingField,
  error,
  onInlineSave,
  onInlineCancel,
  onInlineEdit,
  onEdit,
  onDelete,
  removeItemFromGroup,
  items,
}: TableColumnsProps<T, G> & { items: T[] }) {
  return [
    {
      header: 'ID',
      accessor: (group: G) => (
        <IdColumn
          item={group}
          isItem={false}
          mode={mode}
          inlineEditingId={inlineEditingId}
          inlineEditingField={inlineEditingField}
          onInlineSave={onInlineSave}
          onInlineCancel={onInlineCancel}
          onInlineEdit={onInlineEdit}
          error={error}
        />
      )
    },
    {
      header: 'Members',
      accessor: (group: G) => (
        <div className="flex flex-wrap gap-1">
          {group.members
            .map(memberId => items.find(i => i.id === memberId))
            .filter(Boolean)
            .map(item => (
              <RemovableTag
                key={item!.id}
                id={item!.id}
                onRemove={() => removeItemFromGroup(item!.id, group.id)}
                variant="gray"
              />
            ))}
        </div>
      )
    },
    {
      header: 'Actions',
      accessor: (group: G) => (
        <TableRowActions
          onEdit={() => onEdit(group.id)}
          onDelete={() => onDelete(group.id)}
        />
      ),
      align: 'right' as const
    }
  ];
}
