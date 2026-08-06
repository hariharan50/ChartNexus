import pixelmatch from 'pixelmatch';
import { writeFileSync } from 'node:fs';
import { PNG } from 'pngjs';

export interface ComparisonResult {
  mismatchedPixels: number;
  totalPixels: number;
}

/**
 * Pixel-compares two PNG buffers, writing a highlighted diff image.
 *
 * Different page heights are a difference in themselves, so rather than
 * failing to compare, both images are padded to the larger canvas and the
 * empty region counts as mismatched.
 */
export function comparePng(a: Buffer, b: Buffer, diffPath: string): ComparisonResult {
  const left = PNG.sync.read(a);
  const right = PNG.sync.read(b);

  const width = Math.max(left.width, right.width);
  const height = Math.max(left.height, right.height);

  const canvasA = pad(left, width, height);
  const canvasB = pad(right, width, height);
  const diff = new PNG({ width, height });

  const mismatchedPixels = pixelmatch(canvasA.data, canvasB.data, diff.data, width, height, {
    threshold: 0.1
  });

  writeFileSync(diffPath, PNG.sync.write(diff));

  return { mismatchedPixels, totalPixels: width * height };
}

function pad(source: PNG, width: number, height: number): PNG {
  if (source.width === width && source.height === height) return source;

  // Magenta, so padding shows up unmistakably in the diff rather than reading
  // as a subtle background change.
  const canvas = new PNG({ width, height });
  for (let i = 0; i < canvas.data.length; i += 4) {
    canvas.data[i] = 255;
    canvas.data[i + 1] = 0;
    canvas.data[i + 2] = 255;
    canvas.data[i + 3] = 255;
  }
  PNG.bitblt(source, canvas, 0, 0, source.width, source.height, 0, 0);
  return canvas;
}
