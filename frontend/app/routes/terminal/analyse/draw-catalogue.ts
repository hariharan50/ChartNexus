/**
 * What the rail shows, and in what order.
 *
 * Eight buttons for 43 tools. The grouping is the only thing that makes that
 * usable: a reader looking for a Gann fan does not scan 43 glyphs, they reach
 * for "Fibonacci" and find the Gann section inside it. Sections within a group
 * exist for the same reason one level down.
 *
 * Deliberately separate from the engine's registry. The registry knows how a
 * tool draws; this knows where a reader expects to find it, and those two
 * change for different reasons. It also means the rail can render without
 * importing the engine, which is what keeps the lazy load lazy.
 */

export interface DrawToolDef {
  /** `null` is the plain cursor. */
  id: string | null;
  label: string;
  iconKey: string;
}

export interface DrawSection {
  head?: string;
  tools: DrawToolDef[];
}

export interface DrawGroupDef {
  key: string;
  label: string;
  iconKey: string;
  sections: DrawSection[];
}

export const DRAW_GROUPS: DrawGroupDef[] = [
  {
    key: 'lines',
    label: 'Lines',
    iconKey: 'trend',
    sections: [
      {
        head: 'Lines',
        tools: [
          { id: 'trend-line', label: 'Trend line', iconKey: 'trend' },
          { id: 'ray', label: 'Ray', iconKey: 'ray' },
          { id: 'extended-line', label: 'Extended line', iconKey: 'extended' },
          { id: 'arrow', label: 'Arrow', iconKey: 'arrow' }
        ]
      },
      {
        head: 'Horizontal and vertical',
        tools: [
          { id: 'horizontal-line', label: 'Horizontal line', iconKey: 'hline' },
          { id: 'horizontal-ray', label: 'Horizontal ray', iconKey: 'hray' },
          { id: 'vertical-line', label: 'Vertical line', iconKey: 'vline' },
          { id: 'cross-line', label: 'Cross line', iconKey: 'cross' }
        ]
      }
    ]
  },
  {
    key: 'channels',
    label: 'Channels',
    iconKey: 'channel',
    sections: [
      {
        tools: [
          { id: 'parallel-channel', label: 'Parallel channel', iconKey: 'channel' },
          { id: 'fib-channel', label: 'Fib channel', iconKey: 'fibchannel' }
        ]
      }
    ]
  },
  {
    key: 'fib',
    label: 'Fibonacci',
    iconKey: 'fib',
    sections: [
      {
        head: 'Fibonacci',
        tools: [
          { id: 'fib-retracement', label: 'Fib retracement', iconKey: 'fib' },
          { id: 'fib-extension', label: 'Fib extension', iconKey: 'fib' },
          { id: 'fib-time-zone', label: 'Fib time zone', iconKey: 'fibtime' },
          { id: 'fib-fan', label: 'Fib fan', iconKey: 'fibfan' }
        ]
      },
      {
        head: 'Gann',
        tools: [
          { id: 'gann-fan', label: 'Gann fan', iconKey: 'fibfan' },
          { id: 'gann-box', label: 'Gann box', iconKey: 'rect' }
        ]
      }
    ]
  },
  {
    key: 'shapes',
    label: 'Shapes',
    iconKey: 'rect',
    sections: [
      {
        head: 'Shapes',
        tools: [
          { id: 'rectangle', label: 'Rectangle', iconKey: 'rect' },
          { id: 'rotated-rectangle', label: 'Rotated rectangle', iconKey: 'rotrect' },
          { id: 'ellipse', label: 'Ellipse', iconKey: 'ellipse' },
          { id: 'circle', label: 'Circle', iconKey: 'circle' },
          { id: 'triangle', label: 'Triangle', iconKey: 'triangle' }
        ]
      },
      {
        head: 'Paths',
        tools: [
          { id: 'path', label: 'Path', iconKey: 'path' },
          { id: 'polyline', label: 'Polyline', iconKey: 'polyline' },
          { id: 'arc', label: 'Arc', iconKey: 'arc' },
          { id: 'curve', label: 'Curve', iconKey: 'curve' },
          { id: 'double-curve', label: 'Double curve', iconKey: 'dcurve' }
        ]
      }
    ]
  },
  {
    key: 'cycles',
    label: 'Cycles',
    iconKey: 'sine',
    sections: [
      {
        tools: [
          { id: 'cyclic-lines', label: 'Cyclic lines', iconKey: 'cyclic' },
          { id: 'time-cycles', label: 'Time cycles', iconKey: 'timecycle' },
          { id: 'sine-line', label: 'Sine line', iconKey: 'sine' }
        ]
      }
    ]
  },
  {
    key: 'positions',
    label: 'Forecasting',
    iconKey: 'long',
    sections: [
      {
        tools: [
          { id: 'long-position', label: 'Long position', iconKey: 'long' },
          { id: 'short-position', label: 'Short position', iconKey: 'short' },
          { id: 'forecast', label: 'Forecast', iconKey: 'forecast' }
        ]
      }
    ]
  },
  {
    key: 'measure',
    label: 'Measurers',
    iconKey: 'measure',
    sections: [
      {
        tools: [
          { id: 'price-range', label: 'Price range', iconKey: 'pricerange' },
          { id: 'date-range', label: 'Date range', iconKey: 'daterange' },
          { id: 'measure', label: 'Measure', iconKey: 'measure' }
        ]
      }
    ]
  },
  {
    key: 'marks',
    label: 'Arrows and notes',
    iconKey: 'text',
    sections: [
      {
        head: 'Text and notes',
        tools: [
          { id: 'text', label: 'Text', iconKey: 'text' },
          { id: 'price-label', label: 'Price label', iconKey: 'pricelabel' },
          { id: 'callout', label: 'Callout', iconKey: 'callout' },
          { id: 'flag-mark', label: 'Flag mark', iconKey: 'flag' }
        ]
      },
      {
        head: 'Arrows',
        tools: [
          { id: 'arrow-up', label: 'Arrow up', iconKey: 'arrowup' },
          { id: 'arrow-down', label: 'Arrow down', iconKey: 'arrowdown' }
        ]
      },
      {
        head: 'Brushes',
        tools: [
          { id: 'brush', label: 'Brush', iconKey: 'brush' },
          { id: 'highlighter', label: 'Highlighter', iconKey: 'highlighter' }
        ]
      }
    ]
  }
];

/** Which group owns a tool, so the rail can light the right button. */
export function groupOf(toolId: string | null): string | null {
  if (toolId === null) return null;
  for (const group of DRAW_GROUPS) {
    for (const section of group.sections) {
      if (section.tools.some((tool) => tool.id === toolId)) return group.key;
    }
  }
  return null;
}

/** The catalogue entry for a tool id. */
export function toolOf(toolId: string | null): DrawToolDef | null {
  if (toolId === null) return null;
  for (const group of DRAW_GROUPS) {
    for (const section of group.sections) {
      const found = section.tools.find((tool) => tool.id === toolId);
      if (found) return found;
    }
  }
  return null;
}
