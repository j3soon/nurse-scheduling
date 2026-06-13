/*
 * This file is part of Nurse Scheduling Project, see <https://github.com/j3soon/nurse-scheduling/>.
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

import React, { forwardRef, type InputHTMLAttributes, type WheelEvent } from 'react';

type NumberInputProps = Omit<InputHTMLAttributes<HTMLInputElement>, 'type'> & {
  disableWheelStep?: boolean;
};

function blurOnWheel(event: WheelEvent<HTMLInputElement>) {
  event.currentTarget.blur();
}

const NumberInput = forwardRef<HTMLInputElement, NumberInputProps>(function NumberInput(
  { disableWheelStep = true, onWheel, ...props },
  ref
) {
  return (
    <input
      {...props}
      ref={ref}
      type="number"
      onWheel={(event) => {
        if (disableWheelStep) {
          blurOnWheel(event);
        }
        onWheel?.(event);
      }}
    />
  );
});

export default NumberInput;
