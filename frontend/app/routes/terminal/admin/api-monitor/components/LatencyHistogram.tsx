import { formatCount } from '$contexts/api-monitor/api';
import type { HistogramBucket } from '$contexts/api-monitor/types';
import s from './LatencyHistogram.module.css';

/**
 * How call latency is spread: one bar per stored bucket ("≤ 100 ms", ...).
 *
 * The shape says more than any single percentile: a tight cluster with a long
 * thin tail is a healthy API with the odd slow call; two humps usually mean
 * two different code paths (a cache hit and a miss) behind one endpoint.
 */
export default function LatencyHistogram({ buckets }: { buckets: HistogramBucket[] }) {
  const total = buckets.reduce((sum, bucket) => sum + bucket.count, 0);
  const peak = Math.max(1, ...buckets.map((bucket) => bucket.count));
  if (total === 0) return <p className={s.empty}>No calls in this range.</p>;

  let running = 0;
  return (
    <ol className={s.bars} aria-label="Latency distribution">
      {buckets.map((bucket, index) => {
        running += bucket.count;
        const share = bucket.count / total;
        const label =
          bucket.le_ms === null
            ? `> ${short(buckets[index - 1]?.le_ms ?? 0)}`
            : `≤ ${short(bucket.le_ms)}`;
        return (
          <li key={label} className={s.row}>
            <span className={s.label}>{label}</span>
            <span className={s.track}>
              <span
                className={s.fill}
                style={{ width: `${(bucket.count / peak) * 100}%` }}
                data-slow={bucket.le_ms === null || bucket.le_ms > 1000 ? '' : undefined}
              />
            </span>
            <span
              className={s.count}
              title={`${Math.round((running / total) * 100)}% of calls at or below`}
            >
              {formatCount(bucket.count)}
              <span className={s.share}>
                {share >= 0.001 ? ` ${(share * 100).toFixed(share < 0.1 ? 1 : 0)}%` : ''}
              </span>
            </span>
          </li>
        );
      })}
    </ol>
  );
}

function short(ms: number): string {
  return ms >= 1000 ? `${ms / 1000} s` : `${ms} ms`;
}
