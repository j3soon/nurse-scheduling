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

import { DataType, ShiftAffinityPreference, ShiftCountPreference, ShiftRequestPreference, ShiftTypeRequirementsPreference, ShiftTypeSuccessionsPreference, SHIFT_AFFINITY, SHIFT_COUNT, SHIFT_REQUEST, SHIFT_TYPE_REQUIREMENT, SHIFT_TYPE_SUCCESSIONS } from '@/types/scheduling';
import { SchedulingState } from './schedulingState';

export const applyPeopleHistoryForIdChange = (
  state: SchedulingState,
  dataType: DataType,
  oldId: string,
  newId: string
): SchedulingState => {
  if (dataType !== DataType.SHIFT_TYPES) return state;
  return {
    ...state,
    people: {
      ...state.people,
      items: state.people.items.map(person => ({
        ...person,
        history: person.history?.map(h => h === oldId ? newId : h) || []
      }))
    }
  };
};

export const applyPeopleHistoryForIdDeletion = (
  state: SchedulingState,
  dataType: DataType,
  deletedIds: string[]
): SchedulingState => {
  if (dataType !== DataType.SHIFT_TYPES || deletedIds.length === 0) return state;

  const deletedIdSet = new Set(deletedIds);
  return {
    ...state,
    people: {
      ...state.people,
      items: state.people.items.map(person => ({
        ...person,
        history: person.history?.map(shiftTypeId => deletedIdSet.has(shiftTypeId) ? '' : shiftTypeId) || []
      }))
    }
  };
};

export const applyPreferencesForIdChange = (
  state: SchedulingState,
  dataType: DataType,
  oldId: string,
  newId: string
): SchedulingState => {
  const shiftTypeReqFieldMap = {
    [DataType.DATES]: 'date',
    [DataType.PEOPLE]: 'qualifiedPeople',
    [DataType.SHIFT_TYPES]: 'shiftType'
  };

  const shiftRequestFieldMap = {
    [DataType.DATES]: 'date',
    [DataType.PEOPLE]: 'person',
    [DataType.SHIFT_TYPES]: 'shiftType'
  };

  const shiftTypeSuccessionsFieldMap = {
    [DataType.DATES]: 'date',
    [DataType.PEOPLE]: 'person',
    [DataType.SHIFT_TYPES]: 'pattern'
  };

  const shiftCountFieldMap = {
    [DataType.DATES]: 'countDates',
    [DataType.PEOPLE]: 'person',
    [DataType.SHIFT_TYPES]: 'countShiftTypes'
  };

  const shiftAffinityFieldMap = {
    [DataType.DATES]: ['date'],
    [DataType.PEOPLE]: ['people1', 'people2'],
    [DataType.SHIFT_TYPES]: ['shiftTypes']
  };

  return {
    ...state,
    preferences: state.preferences.map(pref => {
      if (pref.type === SHIFT_TYPE_REQUIREMENT) {
        const fieldName = shiftTypeReqFieldMap[dataType] as keyof ShiftTypeRequirementsPreference;
        const updatedPref: ShiftTypeRequirementsPreference = {
          ...pref,
          [fieldName]: ((pref as ShiftTypeRequirementsPreference)[fieldName] as string[]).map(id => id === oldId ? newId : id)
        };
        if (dataType === DataType.SHIFT_TYPES && updatedPref.shiftTypeCoefficients) {
          updatedPref.shiftTypeCoefficients = updatedPref.shiftTypeCoefficients.map(([id, coefficient]) => [
            id === oldId ? newId : id,
            coefficient
          ]);
        }
        return updatedPref;
      } else if (pref.type === SHIFT_REQUEST) {
        const fieldName = shiftRequestFieldMap[dataType] as keyof ShiftRequestPreference;
        return {
          ...pref,
          [fieldName]: ((pref as ShiftRequestPreference)[fieldName] as string[]).map(id => id === oldId ? newId : id)
        };
      } else if (pref.type === SHIFT_TYPE_SUCCESSIONS) {
        const fieldName = shiftTypeSuccessionsFieldMap[dataType] as keyof ShiftTypeSuccessionsPreference;
        return {
          ...pref,
          [fieldName]: ((pref as ShiftTypeSuccessionsPreference)[fieldName] as string[]).map(id => id === oldId ? newId : id)
        };
      } else if (pref.type === SHIFT_COUNT) {
        const fieldName = shiftCountFieldMap[dataType] as keyof ShiftCountPreference;
        const updatedPref: ShiftCountPreference = {
          ...pref,
          [fieldName]: ((pref as ShiftCountPreference)[fieldName] as string[]).map(id => id === oldId ? newId : id)
        };
        if (dataType === DataType.SHIFT_TYPES && updatedPref.countShiftTypeCoefficients) {
          updatedPref.countShiftTypeCoefficients = updatedPref.countShiftTypeCoefficients.map(([id, coefficient]) => [
            id === oldId ? newId : id,
            coefficient
          ]);
        }
        return updatedPref;
      } else if (pref.type === SHIFT_AFFINITY) {
        const fieldNames = shiftAffinityFieldMap[dataType];
        const updatedPref = { ...pref } as ShiftAffinityPreference;
        fieldNames.forEach(fieldName => {
          const key = fieldName as keyof ShiftAffinityPreference;
          const value = (pref as ShiftAffinityPreference)[key];
          if (Array.isArray(value)) {
            (updatedPref[key] as string[]) = value.map((id: string) => id === oldId ? newId : id);
          }
        });
        return updatedPref;
      }
      return pref;
    })
  };
};

export const applyPreferencesForIdDeletion = (
  state: SchedulingState,
  dataType: DataType,
  deletedIds: string[]
): SchedulingState => {
  // Return early if no IDs to delete
  if (deletedIds.length === 0) {
    return state;
  }

  const deletedIdsSet = new Set(deletedIds);

  const shiftTypeReqFieldMap = {
    [DataType.DATES]: 'date',
    [DataType.PEOPLE]: 'qualifiedPeople',
    [DataType.SHIFT_TYPES]: 'shiftType'
  };

  const shiftRequestFieldMap = {
    [DataType.DATES]: 'date',
    [DataType.PEOPLE]: 'person',
    [DataType.SHIFT_TYPES]: 'shiftType'
  };

  const shiftTypeSuccessionsFieldMap = {
    [DataType.DATES]: 'date',
    [DataType.PEOPLE]: 'person',
    [DataType.SHIFT_TYPES]: 'pattern'
  };

  const shiftCountFieldMap = {
    [DataType.DATES]: 'countDates',
    [DataType.PEOPLE]: 'person',
    [DataType.SHIFT_TYPES]: 'countShiftTypes'
  };

  const shiftAffinityFieldMap = {
    [DataType.DATES]: ['date'],
    [DataType.PEOPLE]: ['people1', 'people2'],
    [DataType.SHIFT_TYPES]: ['shiftTypes']
  };

  const preferences = state.preferences
    // First, filter out the deleted IDs from array fields and remove matching single-value preferences
    .map(pref => {
      if (pref.type === SHIFT_TYPE_REQUIREMENT) {
        const fieldName = shiftTypeReqFieldMap[dataType] as keyof ShiftTypeRequirementsPreference;
        const updatedPref: ShiftTypeRequirementsPreference = {
          ...pref,
          [fieldName]: ((pref as ShiftTypeRequirementsPreference)[fieldName] as string[]).filter(id => !deletedIdsSet.has(id))
        };
        if (dataType === DataType.SHIFT_TYPES && updatedPref.shiftTypeCoefficients) {
          updatedPref.shiftTypeCoefficients = updatedPref.shiftTypeCoefficients.filter(
            ([id]) => !deletedIdsSet.has(id)
          );
        }
        return updatedPref;
      } else if (pref.type === SHIFT_REQUEST) {
        const fieldName = shiftRequestFieldMap[dataType] as keyof ShiftRequestPreference;
        return {
          ...pref,
          [fieldName]: ((pref as ShiftRequestPreference)[fieldName] as string[]).filter(id => !deletedIdsSet.has(id))
        };
      } else if (pref.type === SHIFT_TYPE_SUCCESSIONS) {
        const fieldName = shiftTypeSuccessionsFieldMap[dataType] as keyof ShiftTypeSuccessionsPreference;
        return {
          ...pref,
          [fieldName]: ((pref as ShiftTypeSuccessionsPreference)[fieldName] as string[]).filter(id => !deletedIdsSet.has(id))
        };
      } else if (pref.type === SHIFT_COUNT) {
        const fieldName = shiftCountFieldMap[dataType] as keyof ShiftCountPreference;
        const updatedPref: ShiftCountPreference = {
          ...pref,
          [fieldName]: ((pref as ShiftCountPreference)[fieldName] as string[]).filter(id => !deletedIdsSet.has(id))
        };
        if (dataType === DataType.SHIFT_TYPES && updatedPref.countShiftTypeCoefficients) {
          updatedPref.countShiftTypeCoefficients = updatedPref.countShiftTypeCoefficients.filter(
            ([id]) => !deletedIdsSet.has(id)
          );
        }
        return updatedPref;
      } else if (pref.type === SHIFT_AFFINITY) {
        const fieldNames = shiftAffinityFieldMap[dataType];
        const updatedPref = { ...pref } as ShiftAffinityPreference;
        fieldNames.forEach(fieldName => {
          const key = fieldName as keyof ShiftAffinityPreference;
          const value = (pref as ShiftAffinityPreference)[key];
          if (Array.isArray(value)) {
            (updatedPref[key] as string[]) = value.filter(id => !deletedIdsSet.has(id));
          }
        });
        return updatedPref;
      }
      return pref;
    })
    // Second, remove preferences with empty required fields
    .filter(pref => {
      if (pref.type === SHIFT_TYPE_REQUIREMENT) {
        return (pref as ShiftTypeRequirementsPreference).date.length > 0 &&
          (pref as ShiftTypeRequirementsPreference).qualifiedPeople.length > 0 &&
          (pref as ShiftTypeRequirementsPreference).shiftType.length > 0;
      } else if (pref.type === SHIFT_REQUEST) {
        return (pref as ShiftRequestPreference).person.length > 0 &&
          (pref as ShiftRequestPreference).date.length > 0 &&
          (pref as ShiftRequestPreference).shiftType.length > 0;
      } else if (pref.type === SHIFT_TYPE_SUCCESSIONS) {
        return (pref as ShiftTypeSuccessionsPreference).person.length > 0 &&
          (pref as ShiftTypeSuccessionsPreference).date.length > 0 &&
          (pref as ShiftTypeSuccessionsPreference).pattern.length > 0;
      } else if (pref.type === SHIFT_COUNT) {
        return (pref as ShiftCountPreference).person.length > 0 &&
          (pref as ShiftCountPreference).countDates.length > 0 &&
          (pref as ShiftCountPreference).countShiftTypes.length > 0;
      } else if (pref.type === SHIFT_AFFINITY) {
        return (pref as ShiftAffinityPreference).date.length > 0 &&
          (pref as ShiftAffinityPreference).people1.length > 0 &&
          (pref as ShiftAffinityPreference).people2.length > 0 &&
          (pref as ShiftAffinityPreference).shiftTypes.length > 0;
      }
      return true;
    });

  return {
    ...state,
    preferences
  };
};

export const applyExportLayoutForIdDeletion = (
  state: SchedulingState,
  dataType: DataType,
  deletedIds: string[]
): SchedulingState => {
  if (deletedIds.length === 0) {
    return state;
  }

  const deletedIdsSet = new Set(deletedIds);
  const filterIds = (ids: string[]) => ids.filter(id => !deletedIdsSet.has(id));

  if (!state.export) {
    return state;
  }

  return {
    ...state,
    export: {
      ...state.export,
      formatting: state.export?.formatting
        ?.map(rule => {
          if (dataType === DataType.PEOPLE && 'people' in rule) {
            return { ...rule, people: filterIds(rule.people) };
          }
          if (dataType === DataType.DATES && 'dates' in rule) {
            return { ...rule, dates: filterIds(rule.dates) };
          }
          if (dataType === DataType.SHIFT_TYPES && 'shiftTypes' in rule) {
            return { ...rule, shiftTypes: filterIds(rule.shiftTypes) };
          }
          return rule;
        })
        .filter(rule => {
          if ('people' in rule && rule.people.length === 0) return false;
          if ('dates' in rule && rule.dates.length === 0) return false;
          if ('shiftTypes' in rule && rule.shiftTypes.length === 0) return false;
          return true;
        }),
      extraColumns: state.export?.extraColumns
        ?.map(rule => {
          if (dataType === DataType.DATES) {
            return { ...rule, countDates: filterIds(rule.countDates) };
          }
          if (dataType === DataType.SHIFT_TYPES) {
            return {
              ...rule,
              countShiftTypes: filterIds(rule.countShiftTypes),
              countShiftTypeCoefficients: rule.countShiftTypeCoefficients?.filter(
                ([id]) => !deletedIdsSet.has(id)
              ),
            };
          }
          return rule;
        })
        .filter(rule => rule.countDates.length > 0 && rule.countShiftTypes.length > 0),
      extraRows: state.export?.extraRows
        ?.map(rule => {
          if (dataType === DataType.PEOPLE) {
            return { ...rule, countPeople: filterIds(rule.countPeople) };
          }
          if (dataType === DataType.SHIFT_TYPES) {
            return { ...rule, countShiftTypes: filterIds(rule.countShiftTypes) };
          }
          return rule;
        })
        .filter(rule => rule.countPeople.length > 0 && rule.countShiftTypes.length > 0)
    }
  };
};

export const applyExportLayoutForIdChange = (
  state: SchedulingState,
  dataType: DataType,
  oldId: string,
  newId: string
): SchedulingState => {
  const renameId = (id: string) => id === oldId ? newId : id;
  const renameIds = (ids: string[]) => ids.map(renameId);

  if (!state.export) {
    return state;
  }

  return {
    ...state,
    export: {
      ...state.export,
      formatting: state.export.formatting?.map(rule => {
        if (dataType === DataType.PEOPLE && 'people' in rule) {
          return { ...rule, people: renameIds(rule.people) };
        }
        if (dataType === DataType.DATES && 'dates' in rule) {
          return { ...rule, dates: renameIds(rule.dates) };
        }
        if (dataType === DataType.SHIFT_TYPES && 'shiftTypes' in rule) {
          return { ...rule, shiftTypes: renameIds(rule.shiftTypes) };
        }
        return rule;
      }),
      extraColumns: state.export.extraColumns?.map(rule => {
        if (dataType === DataType.DATES) {
          return { ...rule, countDates: renameIds(rule.countDates) };
        }
        if (dataType === DataType.SHIFT_TYPES) {
          return {
            ...rule,
            countShiftTypes: renameIds(rule.countShiftTypes),
            countShiftTypeCoefficients: rule.countShiftTypeCoefficients?.map(([id, coefficient]) => [
              renameId(id),
              coefficient
            ]),
          };
        }
        return rule;
      }),
      extraRows: state.export.extraRows?.map(rule => {
        if (dataType === DataType.PEOPLE) {
          return { ...rule, countPeople: renameIds(rule.countPeople) };
        }
        if (dataType === DataType.SHIFT_TYPES) {
          return { ...rule, countShiftTypes: renameIds(rule.countShiftTypes) };
        }
        return rule;
      })
    }
  };
};

export const applyReferencesForIdChange = (
  state: SchedulingState,
  dataType: DataType,
  oldId: string,
  newId: string
): SchedulingState => {
  let nextState = applyPeopleHistoryForIdChange(state, dataType, oldId, newId);
  nextState = applyPreferencesForIdChange(nextState, dataType, oldId, newId);
  nextState = applyExportLayoutForIdChange(nextState, dataType, oldId, newId);
  return nextState;
};

export const applyReferencesForIdDeletion = (
  state: SchedulingState,
  dataType: DataType,
  deletedIds: string[]
): SchedulingState => {
  let nextState = applyPeopleHistoryForIdDeletion(state, dataType, deletedIds);
  nextState = applyPreferencesForIdDeletion(nextState, dataType, deletedIds);
  nextState = applyExportLayoutForIdDeletion(nextState, dataType, deletedIds);
  return nextState;
};
