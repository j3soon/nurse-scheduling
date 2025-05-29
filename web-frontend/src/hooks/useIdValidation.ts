interface Person {
  id: string;
}

interface PeopleGroup {
  id: string;
  members: string[];
}

export function useIdValidation(people: Person[], groups: PeopleGroup[]) {
  const isDuplicateId = (id: string, currentId?: string) => {
    // Use OR here since we also don't want ID conflict between people and groups
    return people.some(person => person.id === id && person.id !== currentId) ||
           groups.some(group => group.id === id && group.id !== currentId);
  };

  return { isDuplicateId };
}
