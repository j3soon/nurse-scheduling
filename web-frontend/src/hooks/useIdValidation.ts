interface Item {
  id: string;
}

interface Group {
  id: string;
  members: string[];
}

export function useIdValidation(items: Item[], groups: Group[]) {
  const isDuplicateId = (id: string, currentId?: string) => {
    // Use OR here since we also don't want ID conflict between items and groups
    return items.some(item => item.id === id && item.id !== currentId) ||
           groups.some(group => group.id === id && group.id !== currentId);
  };

  return { isDuplicateId };
}
