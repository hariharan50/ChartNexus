import InfoWindow, { type InfoTab } from '$shared/ui/InfoWindow';
import g from './FiiDiiGuide.module.css';

/**
 * How to read the FII/DII Summary.
 *
 * Content only — the window's chrome is `$shared/ui/InfoWindow`.
 *
 * Written as a *procedure* rather than a glossary. A reader who does not
 * already know this file does not need each field defined; they need to be told
 * which number to look at first, and what the next one means given the last.
 * The order of the "How to read it" tab is the order the panels sit in on the
 * page, so the guide can be followed with the page open behind it.
 */
export default function FiiDiiGuide({ onClose }: { onClose: () => void }) {
  const tabs: InfoTab[] = [
    {
      id: 'what',
      label: 'What this is',
      content: (
        <div className={g.section}>
          <p className={g.p}>
            Every trading day after the close, NSE publishes who traded what. This page is that
            file, for one session: the four participant groups — foreign institutions (FII),
            domestic institutions (DII), proprietary desks (Pro) and everyone else (Client) — and
            what each of them did.
          </p>

          <h3 className={g.h3}>Two different measurements, never mixed</h3>
          <p className={g.p}>
            The page keeps these apart on purpose, and it matters more than it sounds:
          </p>
          <ul className={g.list}>
            <li>
              <strong>Value</strong> — rupees crore <em>traded</em> on the day. Money in, money out.
              That is the left rail and the Money flow chart.
            </li>
            <li>
              <strong>Positions</strong> — contracts <em>held</em> at the close. That is the board
              and the positioning matrix.
            </li>
          </ul>
          <p className={g.p}>
            A participant can be a net buyer on the day and still hold a net short book. The two
            answer different questions, so they never share a table, a scale, or a unit — and you
            should not compare a crore figure against a contract count.
          </p>

          <h3 className={g.h3}>Why the nets cancel</h3>
          <p className={g.p}>
            Every long is somebody else&rsquo;s short, so the four participants&rsquo; positions in
            any segment sum to zero. When the page warns that a segment does not balance, it is
            telling you the file arrived incomplete — not that something moved.
          </p>
        </div>
      )
    },
    {
      id: 'how',
      label: 'How to read it',
      content: (
        <div className={g.section}>
          <p className={g.p}>
            Work down the page in this order. Each step narrows what the next one has to explain.
          </p>

          <ol className={g.steps}>
            <li>
              <strong>Start with the cash line.</strong> FII and DII cash nets are usually opposed —
              foreigners selling into domestic buying, or the reverse. The question is not
              &ldquo;who bought&rdquo; but <em>which side was bigger</em>, because that is the side
              that moved the index. A day where both are buying is rarer and more bullish than
              either figure alone suggests.
            </li>
            <li>
              <strong>Then the Long/Short gauge.</strong> This is FII index-futures longs divided by
              shorts, and it is the number most traders take away from this file. Below 1 they are
              positioned for a fall, above 1 for a rise; the distance from 1 is the conviction. A
              reading of 0.12 means roughly eight shorts for every long — heavy bearish positioning,
              not a lean.
            </li>
            <li>
              <strong>Compare it with the cash line.</strong> Agreement is a strong signal: selling
              cash <em>and</em> short futures is conviction. Disagreement is more interesting —
              heavy cash selling against a long futures book usually means hedging, not a
              directional view.
            </li>
            <li>
              <strong>Then the positioning matrix.</strong> Sixteen cells, green long and red short.
              Look for who is on the other side of FII: if Client is long everything FII is short,
              retail is taking the other end of the institutional trade, which historically is the
              weaker side.
            </li>
            <li>
              <strong>Finally the derivative segments.</strong> These say <em>how</em> the view is
              expressed. Index options carry far more turnover than index futures, so a large
              options net with a small futures net is a positioning day, not a directional one.
            </li>
          </ol>

          <h3 className={g.h3}>A quick sanity check</h3>
          <p className={g.p}>
            Expand any row in the board to see the legs behind the net. An options net is not the
            sum of its four legs: it is the bullish side minus the bearish one, because a long call
            and a short put both gain when the market rises. If a net looks wrong, that is usually
            why.
          </p>
        </div>
      )
    },
    {
      id: 'limits',
      label: 'What it cannot tell you',
      content: (
        <div className={g.section}>
          <p className={g.p}>
            The honest boundaries. Most bad reads of this file come from asking it something it does
            not answer.
          </p>

          <ul className={g.list}>
            <li>
              <strong>It is not live.</strong> The file is published after the close. Nothing here
              describes what is happening now, and nothing here is tradeable intraday.
            </li>
            <li>
              <strong>It is one session.</strong> A single day&rsquo;s net says little on its own; a
              run of the same direction says a lot. The Cash Market page carries the history — use
              it for trend, and this page for detail.
            </li>
            <li>
              <strong>Positions are not value.</strong> A big contract count in stock options can be
              a small amount of money, and a modest cash figure can move the index more than either.
            </li>
            <li>
              <strong>It says nothing about which stocks.</strong> Stock futures and stock options
              are totals across the whole universe. The file does not name a single symbol.
            </li>
            <li>
              <strong>Hedges look like views.</strong> An FII short futures book may be protecting a
              cash portfolio rather than betting on a fall. The data cannot tell those apart, and
              neither can this page.
            </li>
          </ul>

          <p className={g.note}>
            For education only. Nothing here is investment advice, and institutional positioning is
            not a prediction.
          </p>
        </div>
      )
    }
  ];

  return (
    <InfoWindow
      title="Reading the FII/DII Summary"
      kicker="NSE's daily participant file, and what it will and won't tell you"
      mark="?"
      tabs={tabs}
      onClose={onClose}
    />
  );
}
