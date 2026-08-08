import { useState } from 'react';
import { redirect } from 'react-router';
import { currentUser } from '$contexts/identity/api';
import { createServerFetch } from '$shared/api/server-fetch';
import { requestIdContext } from '../../middleware/context';
import ChatBubble from './components/ChatBubble';
import ChecklistRows from './components/ChecklistRows';
import CtaLink from './components/CtaLink';
import FaqAccordion from './components/FaqAccordion';
import FeatureGrid from './components/FeatureGrid';
import Hero from './components/Hero';
import LandingFooter from './components/LandingFooter';
import LandingNav from './components/LandingNav';
import ProofGrid from './components/ProofGrid';
import Section from './components/Section';
import StackBar from './components/StackBar';
import SupportBanner from './components/SupportBanner';
import TrustBar from './components/TrustBar';
import ChainWidget from './components/widgets/ChainWidget';
import { CLOSING, HERO } from './copy';
import { fixtureFor } from './fixtures';
import s from './route.module.css';
import type { Route } from './+types/route';

/**
 * The marketing landing page — what `/` shows a visitor who is not signed in.
 *
 * Before this existed `/` was a bare redirect to `/dashboard`, which the
 * terminal guard then bounced to `/login`. A stranger typing the domain in
 * reached a sign-in form having never been told what the product was.
 *
 * Signed-in visitors still skip it: they came for the terminal, not the pitch.
 */
export async function loader({ request, context }: Route.LoaderArgs) {
  const fetcher = createServerFetch(request, context.get(requestIdContext));

  let signedIn = false;
  try {
    await currentUser(fetcher);
    signedIn = true;
  } catch {
    // Every failure renders the marketing page, not just 401/403 — unlike the
    // terminal guard, which re-throws. This page is the front door: if the API
    // is unreachable it must still serve, because a 500 on the homepage is a
    // worse outcome than showing a signed-in visitor one extra click.
  }

  // Outside the `try` on purpose. `redirect()` throws a Response, so throwing
  // it inside would land in the `catch` above and be swallowed as "signed out".
  if (signedIn) throw redirect('/dashboard', 303);
  return null;
}

export const meta: Route.MetaFunction = () => [
  { title: 'MarketCompass — NSE options analytics with provenance on every number' },
  {
    name: 'description',
    content:
      'Option chain, PCR, max pain, OI build-up and gamma exposure for NIFTY, BANKNIFTY and ' +
      'SENSEX. Every figure declares whether it is live, cached or simulated. Read-only — it ' +
      'never places an order.'
  },
  { property: 'og:type', content: 'website' },
  { property: 'og:title', content: 'MarketCompass — NSE options analytics' },
  {
    property: 'og:description',
    content: 'Options analytics for NIFTY, BANKNIFTY and SENSEX, with provenance on every number.'
  },
  { name: 'twitter:card', content: 'summary' }
];

export default function Landing() {
  // The hero graphic is the real chain widget, and its index tabs work — the
  // one piece of state on the page.
  const [index, setIndex] = useState('NIFTY');
  const fixture = fixtureFor(index);

  return (
    <div className={s.landing}>
      <LandingNav />

      <Hero>
        <ChainWidget selected={index} onSelect={setIndex} fixture={fixture} />
      </Hero>

      <TrustBar />

      <FeatureGrid
        eyebrow="What you get"
        heading={
          <>
            Everything the chain says, <strong>already worked out.</strong>
          </>
        }
      />

      <ChecklistRows
        eyebrow="Included"
        heading={
          <>
            No trial timer, <strong>no card, no broker required.</strong>
          </>
        }
      />

      <Section
        eyebrow="Provenance"
        heading={
          <>
            A stale number that looks live <strong>is worse than no number.</strong>
          </>
        }
        lead="Every response says which rung of the ladder it came from — a fresh broker read, a cached one, the last good value, or the simulator — and how old it is. Degraded data is labelled rather than hidden."
      />

      <ProofGrid />

      <SupportBanner />

      <FaqAccordion
        eyebrow="FAQ"
        heading={
          <>
            The questions <strong>worth asking first.</strong>
          </>
        }
      />

      <StackBar />

      <Section
        eyebrow={CLOSING.eyebrow}
        heading={
          <>
            {CLOSING.headingLead} <strong>{CLOSING.headingKeyword}</strong>
          </>
        }
        lead={CLOSING.lead}
        panel
      >
        <div className={s.closingActions}>
          <CtaLink to={HERO.primary.to} tone="solid" size="lg">
            {HERO.primary.label}
          </CtaLink>
          <CtaLink to={HERO.secondary.to} tone="ghost" size="lg">
            {HERO.secondary.label}
          </CtaLink>
        </div>
      </Section>

      <LandingFooter />
      <ChatBubble />
    </div>
  );
}
