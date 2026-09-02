import { BarChart, GaugeChart, LineChart } from 'echarts/charts';
import {
  AxisPointerComponent,
  DataZoomInsideComponent,
  GridComponent,
  MarkAreaComponent,
  MarkLineComponent,
  TooltipComponent
} from 'echarts/components';
import * as echarts from 'echarts/core';
import { SVGRenderer } from 'echarts/renderers';

/**
 * The single place ECharts features are registered.
 *
 * ECharts' tree-shaken build only draws what has been `use`d. Registering here
 * rather than inside a component keeps the bundle honest — one list to read
 * when asking "why is the chart chunk this size" — and guarantees registration
 * has happened before any chart initialises, whatever import order Vite picks.
 *
 * **SVG, not canvas.** A canvas is a bitmap sized once from `devicePixelRatio`,
 * and ECharts reads that ratio a single time when the instance is built — it
 * cannot be changed on a live chart, and `resize()` reuses the stored value. So
 * the moment the reader zooms the browser (which *is* a devicePixelRatio
 * change) the bitmap no longer matches the physical pixels and the compositor
 * resamples it: soft bar edges, dashed outlines smeared into grey, hatch
 * stripes dissolved. That was the OI chart's "goes blurry when I zoom".
 *
 * SVG has no backing store, so there is no resolution to get stale. The browser
 * rasterises it fresh at whatever zoom, display scaling or print DPI it is
 * currently at, which makes the whole class of bug impossible rather than
 * something to detect and rebuild around.
 *
 * The cost is that every mark becomes a DOM node. That is the right trade at
 * this scale — a hundred-odd bars over a few series, repainted on a poll
 * measured in seconds — but it would be the wrong one for tick-level streaming
 * or many-thousand-element series. Price charts are unaffected either way:
 * `charts/tv/LwChart` is lightweight-charts, which owns its own canvas and
 * handles pixel ratio itself.
 */
echarts.use([
  BarChart,
  // Multi OI & Volume plots one line per contract plus a futures overlay.
  LineChart,
  // The Max Pain sentiment gauge: a graded arc with a pointer. Hand-rolling the
  // ticks, the banded axis line and the rotated band labels in SVG would be a
  // few hundred lines of geometry that this draws for free.
  GaugeChart,
  GridComponent,
  TooltipComponent,
  // Lets `echarts.connect` drive one crosshair across the three stacked charts
  // on that page, so a reading at 11:30 is a reading at 11:30 on all of them.
  AxisPointerComponent,
  // Wheel-to-zoom and drag-to-pan on the time axis. `echarts.connect` also syncs
  // the zoom window across a group, so zooming one panel of the Price vs OI grid
  // zooms all of them to the same window. Inside-only: no slider chrome, and the
  // toolbox/select variants (and their extra components) are not needed.
  DataZoomInsideComponent,
  MarkLineComponent,
  MarkAreaComponent,
  SVGRenderer
]);

export { echarts };
export type { ECharts, EChartsCoreOption } from 'echarts/core';
