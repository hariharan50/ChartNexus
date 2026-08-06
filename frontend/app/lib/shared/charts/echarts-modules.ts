import { BarChart } from 'echarts/charts';
import {
  GridComponent,
  MarkAreaComponent,
  MarkLineComponent,
  TooltipComponent
} from 'echarts/components';
import * as echarts from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';

/**
 * The single place ECharts features are registered.
 *
 * ECharts' tree-shaken build only draws what has been `use`d. Registering here
 * rather than inside a component keeps the bundle honest — one list to read
 * when asking "why is the chart chunk this size" — and guarantees registration
 * has happened before any chart initialises, whatever import order Vite picks.
 *
 * Canvas, not SVG: the OI chart redraws on every poll and canvas is cheaper for
 * dense bars. Add a renderer here if a print/export path ever needs SVG.
 */
echarts.use([
  BarChart,
  GridComponent,
  TooltipComponent,
  MarkLineComponent,
  MarkAreaComponent,
  CanvasRenderer
]);

export { echarts };
export type { ECharts, EChartsCoreOption } from 'echarts/core';
