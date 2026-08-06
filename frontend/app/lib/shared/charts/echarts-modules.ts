import { BarChart, LineChart } from 'echarts/charts';
import {
  AxisPointerComponent,
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
  // Multi OI & Volume plots one line per contract plus a futures overlay.
  LineChart,
  GridComponent,
  TooltipComponent,
  // Lets `echarts.connect` drive one crosshair across the three stacked charts
  // on that page, so a reading at 11:30 is a reading at 11:30 on all of them.
  AxisPointerComponent,
  MarkLineComponent,
  MarkAreaComponent,
  CanvasRenderer
]);

export { echarts };
export type { ECharts, EChartsCoreOption } from 'echarts/core';
