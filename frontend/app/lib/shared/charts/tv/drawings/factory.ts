import type { DrawingPrimitive } from './DrawingPrimitive';
import { FibRetracementPrimitive } from './FibRetracementPrimitive';
import { HorizontalLinePrimitive } from './HorizontalLinePrimitive';
import { RectanglePrimitive } from './RectanglePrimitive';
import { TextPrimitive } from './TextPrimitive';
import { TrendLinePrimitive } from './TrendLinePrimitive';
import type { Drawing } from './types';

/** The one place that knows which `Drawing` kind maps to which primitive class. */
export function buildPrimitive(drawing: Drawing): DrawingPrimitive {
  switch (drawing.kind) {
    case 'trendline':
      return new TrendLinePrimitive(drawing.a, drawing.b, drawing.color);
    case 'horizontal':
      return new HorizontalLinePrimitive(drawing.price, drawing.color);
    case 'fib':
      return new FibRetracementPrimitive(drawing.a, drawing.b, drawing.color);
    case 'rectangle':
      return new RectanglePrimitive(drawing.a, drawing.b, drawing.color);
    case 'text':
      return new TextPrimitive(drawing.at, drawing.text, drawing.color);
  }
}
