import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import type { FlowSegment, OiGroup, OiParticipant, OiRow } from '$contexts/market-breadth/types';
import { OiBoard } from '../../app/routes/terminal/future-lab/analysis/fii-dii-summary';

/**
 * The FII/DII Summary board.
 *
 * Two things here are only wrong on screen and never throw, which is why they
 * are pinned in a rendering test rather than a unit one:
 *
 * * the band cell's `rowSpan`, which has to grow when a row inside the band
 *   expands its leg breakdown — get it wrong and the band stops short and the
 *   table shears sideways; and
 * * the view toggle, which must relabel the columns without moving a number.
 */

function row(participant: OiParticipant, segment: FlowSegment, over: Partial<OiRow> = {}): OiRow {
  return {
    participant,
    segment,
    net: 505_000,
    previous_net: 501_000,
    change: 4_000,
    legs: {
      long: 900_000,
      short: 395_000,
      call_long: null,
      call_short: null,
      put_long: null,
      put_short: null,
      total: 1_295_000
    },
    ...over
  };
}

function optionRow(participant: OiParticipant, segment: FlowSegment): OiRow {
  return row(participant, segment, {
    net: -895_000,
    previous_net: -899_000,
    change: 4_069,
    legs: {
      long: null,
      short: null,
      call_long: 120_000,
      call_short: 700_000,
      put_long: 500_000,
      put_short: 185_000,
      total: 1_505_000
    }
  });
}

const SEGMENTS: FlowSegment[] = [
  'index_futures',
  'index_options',
  'stock_futures',
  'stock_options'
];

function participantGroup(participant: OiParticipant): OiGroup {
  const rows = SEGMENTS.map((segment) =>
    segment.endsWith('options') ? optionRow(participant, segment) : row(participant, segment)
  );
  return {
    key: participant,
    rows,
    net: rows.reduce((total, entry) => total + entry.net, 0),
    change: rows.reduce((total, entry) => total + entry.change, 0)
  };
}

const PARTICIPANT_GROUPS = (['fii', 'pro', 'client', 'dii'] as OiParticipant[]).map(
  participantGroup
);

/** The same rows, banded the other way — one segment, four participants. */
const SEGMENT_GROUPS: OiGroup[] = SEGMENTS.map((segment) => {
  const rows = (['fii', 'pro', 'client', 'dii'] as OiParticipant[]).map((participant) =>
    segment.endsWith('options') ? optionRow(participant, segment) : row(participant, segment)
  );
  return { key: segment, rows, net: 0, change: 0 };
});

describe('the banded board', () => {
  it('bands each participant across its four segment rows', () => {
    render(<OiBoard groups={PARTICIPANT_GROUPS} view="participant" />);

    const cells = screen.getAllByRole('cell', { name: /^FII/ });
    expect(cells[0]).toHaveAttribute('rowspan', '4');
  });

  it('names the two grouping columns the right way round', () => {
    const { rerender } = render(<OiBoard groups={PARTICIPANT_GROUPS} view="participant" />);
    const headers = () =>
      screen.getAllByRole('columnheader').map((cell) => cell.textContent?.trim());

    expect(headers().slice(0, 2)).toEqual(['Participant', 'Segment']);

    rerender(<OiBoard groups={SEGMENT_GROUPS} view="segment" />);
    expect(headers().slice(0, 2)).toEqual(['Segment', 'Participant']);
  });

  it('shows the same number of data rows in either grouping', () => {
    const { rerender } = render(<OiBoard groups={PARTICIPANT_GROUPS} view="participant" />);
    const dataRows = () => screen.getAllByRole('row').length;

    const banded = dataRows();
    rerender(<OiBoard groups={SEGMENT_GROUPS} view="segment" />);

    expect(dataRows()).toBe(banded);
  });

  it('prints yesterday and the change beside every net', () => {
    render(<OiBoard groups={PARTICIPANT_GROUPS} view="participant" />);

    const cells = screen.getAllByRole('row')[1]!;
    // 505,000 contracts reads as lakhs; the change stays a plain count and is
    // always signed.
    expect(within(cells).getByText('5.05 L')).toBeInTheDocument();
    expect(within(cells).getByText('5.01 L')).toBeInTheDocument();
    expect(within(cells).getByText('+4,000')).toBeInTheDocument();
  });

  it('shows the segment balance on a segment band, where it means something', () => {
    render(<OiBoard groups={SEGMENT_GROUPS} view="segment" />);

    // Every long is somebody's short, so a complete segment nets to zero.
    expect(screen.getAllByText(/balance 0/)).toHaveLength(SEGMENTS.length);
  });

  it('does not claim a balance on a participant band, which sums nothing real', () => {
    render(<OiBoard groups={PARTICIPANT_GROUPS} view="participant" />);

    expect(screen.queryByText(/balance/)).not.toBeInTheDocument();
  });
});

describe('the leg breakdown', () => {
  it('grows the band so it still spans its own rows when one expands', async () => {
    const user = userEvent.setup();
    render(<OiBoard groups={[participantGroup('fii')]} view="participant" />);
    const cell = screen.getAllByRole('cell', { name: /^FII/ })[0]!;

    expect(cell).toHaveAttribute('rowspan', '4');
    await user.click(screen.getByRole('button', { name: /Index Options/ }));

    // Four rows plus the one that just opened — a band that stayed at 4 would
    // shear the rest of the table across by a column.
    expect(cell).toHaveAttribute('rowspan', '5');
  });

  it('shows the four option legs on an options row', async () => {
    const user = userEvent.setup();
    render(<OiBoard groups={[participantGroup('fii')]} view="participant" />);

    await user.click(screen.getByRole('button', { name: /Index Options/ }));

    expect(screen.getByText('Call long')).toBeInTheDocument();
    expect(screen.getByText('Put short')).toBeInTheDocument();
    expect(screen.queryByText('Long')).not.toBeInTheDocument();
  });

  it('shows the two futures legs on a futures row', async () => {
    const user = userEvent.setup();
    render(<OiBoard groups={[participantGroup('fii')]} view="participant" />);

    await user.click(screen.getByRole('button', { name: /Index Futures/ }));

    expect(screen.getByText('Long')).toBeInTheDocument();
    expect(screen.getByText('Short')).toBeInTheDocument();
    expect(screen.queryByText('Call long')).not.toBeInTheDocument();
  });

  it('collapses again on a second click', async () => {
    const user = userEvent.setup();
    render(<OiBoard groups={[participantGroup('fii')]} view="participant" />);
    const toggle = screen.getByRole('button', { name: /Index Futures/ });

    await user.click(toggle);
    expect(toggle).toHaveAttribute('aria-expanded', 'true');

    await user.click(toggle);
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByText('Total book')).not.toBeInTheDocument();
  });
});
