/**
 * Registers the 43 built-in tools, once.
 *
 * Idempotent because the engine module can be imported from more than one chart
 * pane, and a second `register()` of the same id would be harmless but a second
 * *pass* over all 43 is pure waste on every extra pane in a 2x2 grid.
 */

import { has } from '../registry';
import { registerCycles } from './cycles';
import { registerFib } from './fib';
import { registerLines } from './lines';
import { registerMarks } from './marks';
import { registerMeasures } from './measures';
import { registerPositions } from './positions';
import { registerShapes } from './shapes';

let done = false;

export function registerBuiltins(): void {
  if (done || has('trend-line')) {
    done = true;
    return;
  }
  registerLines();
  registerShapes();
  registerFib();
  registerCycles();
  registerPositions();
  registerMeasures();
  registerMarks();
  done = true;
}
