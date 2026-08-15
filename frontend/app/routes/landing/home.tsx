import { useState } from 'react';
import { Link } from 'react-router';
import { cx } from '$shared/ui/cx';
import ChainWidget from './components/widgets/ChainWidget';
import { Icon, IconCheck } from './components/icons';
import { HERO_STATS, HOME_HIGHLIGHTS, PROVENANCE_LEGEND } from './content';
import { fixtureFor } from './fixtures';
import s from './route.module.css';
import type { Route } from './+types/home';

export const meta: Route.MetaFunction = () => [
  { title: 'MarketCompass — NSE options analytics with provenance on every number' },
  {
    name: 'description',
    content:
      'Option chain, PCR, max pain, OI build-up, gamma and vega exposure and the ATM straddle ' +
      'for NIFTY, BANKNIFTY and SENSEX. Every figure declares whether it is live, cached or ' +
      'simulated. Read-only — it never places an order.'
  },
  { property: 'og:type', content: 'website' },
  { property: 'og:title', content: 'MarketCompass — NSE options analytics' },
  {
    property: 'og:description',
    content: 'Options analytics for NIFTY, BANKNIFTY and SENSEX, with provenance on every number.'
  },
  { name: 'twitter:card', content: 'summary' }
];

export default function Home() {
  const [index, setIndex] = useState('NIFTY');
  const fixture = fixtureFor(index);

  return (
    <>
      <section className={s.hero}>
        <div className={cx(s.shell, s.heroGrid)}>
          <div>
            <span className={s.badge}>
              <span className={s.badgeDot} aria-hidden="true" />
              Provenance on <span className={s.badgeHi}>every number</span>
            </span>

            <p className={s.heroLabel}>NSE Options Analytics</p>
            <h1 className={s.heroTitle}>
              Read the option chain without guessing where the numbers came from.
            </h1>
            <p className={s.heroLead}>
              Open interest, put-call ratio, max pain, gamma and vega exposure and the ATM straddle
              for NIFTY, BANKNIFTY and SENSEX — each figure stamped live, cached or simulated, with
              its age. Free, and it works before you connect a broker.
            </p>

            <div className={s.heroActions}>
              <Link className={cx(s.btn, s.btnPrimary, s.btnLg)} to="/register">
                Create free account →
              </Link>
              <Link className={cx(s.btn, s.btnGhost, s.btnLg)} to="/login">
                Sign in
              </Link>
            </div>

            <p className={s.heroFine}>
              No broker account needed. No card. MarketCompass is read-only — it reads the chain and
              cannot place an order, hold funds, or give SEBI-regulated advice.
            </p>

            <div className={s.stats}>
              {HERO_STATS.map((stat) => (
                <div key={stat.caption}>
                  <div className={cx(s.statValue, 'mc-numeric')}>{stat.value}</div>
                  <div className={s.statCaption}>{stat.caption}</div>
                </div>
              ))}
            </div>
          </div>

          {/* Trading-desk mock — the real chain widget, held to its own provenance
            guarantee (the badge reads "Simulated"). */}
          <div className={s.desk}>
            <div className={s.deskHead}>
              <div>
                <p className={s.deskLabel}>Trading desk</p>
                <h2 className={s.deskTitle}>{fixture.label} option chain</h2>
              </div>
              <span className={s.deskPill}>
                <i aria-hidden="true" />
                Simulated data
              </span>
            </div>

            <ChainWidget selected={index} onSelect={setIndex} fixture={fixture} />

            <div className={s.deskNote}>
              <IconCheck />
              Every figure here is stamped with where it came from and how old it is — the same
              guarantee the terminal makes on live data.
            </div>
          </div>
        </div>
      </section>

      {/* Teaser cards linking to the deeper pages. */}
      <section className={s.section}>
        <div className={s.shell}>
          <div className={s.sectionHead}>
            <p className={s.eyebrow}>Take a look around</p>
            <h2 className={s.h2}>Three ways to read the desk.</h2>
          </div>
          <div className={cx(s.grid, s.grid3)}>
            {HOME_HIGHLIGHTS.map((h) => (
              <Link key={h.title} to={h.to} className={cx(s.card, s.cardLink)}>
                <span className={s.tile}>
                  <Icon name={h.glyph} />
                </span>
                <h3 className={s.cardTitle}>{h.title}</h3>
                <p className={s.cardBody}>{h.body}</p>
                <span className={s.cardCue}>Explore →</span>
              </Link>
            ))}
          </div>
        </div>
      </section>

      {/* Provenance legend — the core promise, on the front page. */}
      <section className={s.section}>
        <div className={s.shell}>
          <div className={s.sectionHead}>
            <p className={s.eyebrow}>Provenance on every number</p>
            <h2 className={s.h2}>Know what the number is — and where it came from.</h2>
            <p className={s.lead}>
              Every figure carries one of these four stamps, with its age. A degraded number is
              labelled, never disguised.
            </p>
          </div>
          <div className={s.legend}>
            {PROVENANCE_LEGEND.map((p) => (
              <div key={p.label} className={s.legendItem}>
                <span className={cx(s.legendChip, s[p.tone])}>{p.label}</span>
                <p className={s.legendMeaning}>{p.meaning}</p>
              </div>
            ))}
          </div>
        </div>
      </section>
    </>
  );
}
