import { useEffect, useState, type ReactNode } from 'react';
import { Link } from 'react-router';
import { cx } from '$shared/ui/cx';
import w from './AgentInfoWindow.module.css';

/** Which agent's documentation to show. Tones and content follow from this. */
export type AgentKey = 'hella' | 'stryx' | 'hugin';

type DocTab = 'about' | 'usage' | 'architecture';

const DOC_TABS: { id: DocTab; label: string }[] = [
  { id: 'about', label: 'What it does' },
  { id: 'usage', label: 'How to use' },
  { id: 'architecture', label: 'Architecture' }
];

type ArchNode = { x: number; y: number; label: string; sub: string; accent?: boolean };
type ArchSpec = { intro: ReactNode; nodes: ArchNode[]; edges: string[]; steps: ReactNode };
type AgentDoc = {
  mark: string;
  title: string;
  kicker: string;
  about: ReactNode;
  usage: ReactNode;
  arch: ArchSpec;
};

/**
 * A floating, dismissible window explaining an AI Console agent — what it does,
 * how to use it, and a small architecture diagram. Shared by HELLA, STRYX and
 * HUGIN; it inherits the page's --mc-accent so it tones to each agent. Opened
 * from the "!" button in the console header.
 */
export default function AgentInfoWindow({
  agent,
  onClose
}: {
  agent: AgentKey;
  onClose: () => void;
}) {
  const [tab, setTab] = useState<DocTab>('about');
  const doc = AGENT_DOCS[agent];

  // Escape closes the window, and the body is locked so the page behind it does
  // not scroll while the modal is open.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = prev;
    };
  }, [onClose]);

  return (
    <div className={w.overlay}>
      <button
        type="button"
        className={w.backdrop}
        aria-label="Close"
        tabIndex={-1}
        onClick={onClose}
      />
      <div className={w.window} role="dialog" aria-modal="true" aria-labelledby="agent-doc-title">
        <header className={w.head}>
          <div className={w.titleWrap}>
            <span className={w.mark}>{doc.mark}</span>
            <div>
              <h2 id="agent-doc-title" className={w.title}>
                {doc.title}
              </h2>
              <p className={w.kicker}>{doc.kicker}</p>
            </div>
          </div>
          <button type="button" className={w.close} aria-label="Close" onClick={onClose}>
            ×
          </button>
        </header>

        <div className={w.tabs} role="tablist" aria-label="Agent documentation">
          {DOC_TABS.map((t) => (
            <button
              key={t.id}
              type="button"
              role="tab"
              aria-selected={tab === t.id}
              className={cx(w.tab, tab === t.id && w.tabActive)}
              onClick={() => setTab(t.id)}
            >
              {t.label}
            </button>
          ))}
        </div>

        <div className={w.body}>
          {tab === 'about' ? (
            doc.about
          ) : tab === 'usage' ? (
            doc.usage
          ) : (
            <div className={w.section}>
              <p className={w.p}>{doc.arch.intro}</p>
              <ArchDiagram nodes={doc.arch.nodes} edges={doc.arch.edges} />
              <h3 className={w.h3}>The flow</h3>
              {doc.arch.steps}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/** A compact, theme-aware SVG built from labelled boxes and arrow paths. */
function ArchDiagram({ nodes, edges }: { nodes: ArchNode[]; edges: string[] }) {
  return (
    <div className={w.archWrap}>
      <svg viewBox="0 0 540 250" className={w.arch} role="img" aria-label="Architecture diagram">
        <defs>
          <marker
            id="agent-arrow"
            viewBox="0 0 10 10"
            refX="8"
            refY="5"
            markerWidth="7"
            markerHeight="7"
            orient="auto-start-reverse"
          >
            <path d="M0 0L10 5L0 10z" className={w.archArrowHead} />
          </marker>
        </defs>

        {nodes.map((n, i) => (
          <g key={i}>
            <rect
              x={n.x}
              y={n.y}
              width="150"
              height="54"
              rx="10"
              className={n.accent ? w.archBoxAccent : w.archBox}
            />
            <text x={n.x + 75} y={n.y + 22} textAnchor="middle" className={w.archLabel}>
              {n.label}
            </text>
            <text x={n.x + 75} y={n.y + 39} textAnchor="middle" className={w.archSub}>
              {n.sub}
            </text>
          </g>
        ))}

        <g className={w.archLine} markerEnd="url(#agent-arrow)" fill="none">
          {edges.map((d, i) => (
            <path key={i} d={d} />
          ))}
        </g>
      </svg>
    </div>
  );
}

// Shared arrow paths — the three agents use the same six-box layout, so the
// edges are identical; only the box labels differ.
const LOOP_EDGES = [
  'M165 47 H190', // top-left → top-mid
  'M345 47 H370', // top-mid → top-right
  'M450 74 V105', // top-right → bottom-right (down)
  'M370 137 H350', // bottom-right → bottom-mid (left)
  'M190 137 H170', // bottom-mid → bottom-left (left)
  'M270 105 V74' // bottom-mid → top-mid (up, feedback)
];

const AGENT_DOCS: Record<AgentKey, AgentDoc> = {
  hella: {
    mark: 'H',
    title: 'About Hella',
    kicker: 'Your soft-spoken markets analyst.',
    about: (
      <div className={w.section}>
        <p className={w.lead}>
          Hella is an <strong>independent markets analyst</strong> that reads the live tape for you —
          open interest, price action, key levels and risk — and walks you through it in plain
          language. She explains what she sees; she doesn&apos;t hand out orders.
        </p>
        <h3 className={w.h3}>Where she fits</h3>
        <p className={w.p}>
          One of three sibling agents: <strong>Hella reads</strong> the tape, <strong>STRYX</strong>{' '}
          hunts setups to act on, and <strong>HUGIN</strong> remembers and grades itself over time.
        </p>
        <h3 className={w.h3}>Use cases</h3>
        <ul className={w.list}>
          <li>
            <strong>Understand the tape.</strong> Ask what OI, price and levels are saying for NIFTY,
            SENSEX or BANK NIFTY right now.
          </li>
          <li>
            <strong>Make sense of a call.</strong> Have her explain the reasoning, the risk and which
            levels actually matter.
          </li>
          <li>
            <strong>Learn as you go.</strong> A calm, jargon-light second opinion that teaches while
            it answers.
          </li>
          <li>
            <strong>Stay oriented intraday.</strong> Quick reads on structure and momentum without
            leaving the terminal.
          </li>
        </ul>
      </div>
    ),
    usage: (
      <div className={w.section}>
        <h3 className={w.h3}>Getting started</h3>
        <ol className={w.steps}>
          <li>
            <strong>Add your LLM key.</strong> Hella runs on your own key — set one in{' '}
            <Link to="/settings/ai">Settings → AI</Link>.
          </li>
          <li>
            <strong>Pick an instrument.</strong> Use the NIFTY / SENSEX / BANK NIFTY switcher — each
            keeps its own conversation.
          </li>
          <li>
            <strong>Ask anything.</strong> Type a question or tap a suggestion chip to get going.
          </li>
        </ol>
        <h3 className={w.h3}>Tips</h3>
        <ul className={w.list}>
          <li>
            <strong>Suggestion chips</strong> — quick prompts like &ldquo;Why this call?&rdquo; or
            &ldquo;Which levels matter?&rdquo; get you a fast read.
          </li>
          <li>
            <strong>She shows her work</strong> — small tool chips reveal what she read while she
            reasons.
          </li>
          <li>
            <strong>The thread is saved</strong> per instrument, so you can pick up where you left
            off.
          </li>
        </ul>
        <p className={w.note}>
          Hella is an analyst, not an adviser — she explains the market; the decision stays yours.
        </p>
      </div>
    ),
    arch: {
      intro: (
        <>
          A question is passed to a planner that picks which read-only market tools to use; the tools
          return live OI, price and levels; the model synthesises them into an answer streamed back to
          you — with the conversation kept in a short-lived session memory.
        </>
      ),
      nodes: [
        { x: 15, y: 20, label: 'You ask', sub: 'a question' },
        { x: 195, y: 20, label: 'Planner · LLM', sub: 'picks skills', accent: true },
        { x: 375, y: 20, label: 'Market tools', sub: 'OI · price · levels' },
        { x: 375, y: 110, label: 'Synthesize · LLM', sub: 'reads the tape', accent: true },
        { x: 195, y: 110, label: 'Session memory', sub: 'Redis · per chat' },
        { x: 15, y: 110, label: 'Streamed answer', sub: 'back to you' }
      ],
      edges: LOOP_EDGES,
      steps: (
        <ol className={w.steps}>
          <li>
            <strong>You ask</strong> a question about an instrument.
          </li>
          <li>
            <strong>A planner</strong> decides which read-only tools are worth calling.
          </li>
          <li>
            <strong>Market tools</strong> return live OI, price action and levels.
          </li>
          <li>
            <strong>The model synthesises</strong> them into a plain-language read.
          </li>
          <li>
            <strong>The answer streams</strong> back token by token.
          </li>
          <li>
            <strong>Session memory</strong> keeps the thread so follow-ups have context.
          </li>
        </ol>
      )
    }
  },

  stryx: {
    mark: 'S',
    title: 'About STRYX',
    kicker: 'The opportunity hunter — a call, or NO TRADE.',
    about: (
      <div className={w.section}>
        <p className={w.lead}>
          STRYX is an <strong>aggressive trade-caller</strong>. It scans the flow for an edge and
          hands you a concrete call — entry, stop, target and conviction — or says{' '}
          <strong>NO TRADE</strong> just as fast when there isn&apos;t one. Discipline is built in: a
          daily journal caps how many LIVE calls it will make.
        </p>
        <h3 className={w.h3}>Where it fits</h3>
        <p className={w.p}>
          One of three sibling agents: <strong>Hella</strong> reads the tape, <strong>STRYX acts</strong>{' '}
          on setups, and <strong>HUGIN</strong> remembers and grades itself over time.
        </p>
        <h3 className={w.h3}>Use cases</h3>
        <ul className={w.list}>
          <li>
            <strong>Find a setup now.</strong> Ask if there&apos;s an edge in NIFTY, SENSEX or BANK
            NIFTY and get a defined call or a clean pass.
          </li>
          <li>
            <strong>Get exact levels.</strong> Entry, stop and target so risk is defined before you
            act.
          </li>
          <li>
            <strong>Read the flow.</strong> OI, structure and momentum distilled into a decision.
          </li>
          <li>
            <strong>Stay disciplined.</strong> The 2-LIVE-calls-a-day cap keeps it from over-trading.
          </li>
        </ul>
      </div>
    ),
    usage: (
      <div className={w.section}>
        <h3 className={w.h3}>Getting started</h3>
        <ol className={w.steps}>
          <li>
            <strong>Add your LLM key.</strong> STRYX runs on your own key — set one in{' '}
            <Link to="/settings/ai">Settings → AI</Link>.
          </li>
          <li>
            <strong>Pick an instrument.</strong> Use the NIFTY / SENSEX / BANK NIFTY switcher — each
            keeps its own thread and budget.
          </li>
          <li>
            <strong>Ask for a setup.</strong> Type a question or tap a chip like &ldquo;Any setup
            right now?&rdquo;.
          </li>
        </ol>
        <h3 className={w.h3}>Reading a call</h3>
        <ul className={w.list}>
          <li>
            <strong>Status badge</strong> — every reply is tagged <strong>LIVE</strong>,{' '}
            <strong>WATCHING</strong> or <strong>NO TRADE</strong>.
          </li>
          <li>
            <strong>LIVE-call budget</strong> — the chip in the header shows how many of the day&apos;s
            calls remain (2 by default).
          </li>
          <li>
            <strong>Defined risk</strong> — a LIVE call always carries an entry, stop and target.
          </li>
        </ul>
        <p className={w.note}>
          STRYX surfaces ideas, not advice — size and execution are your call, always with a stop.
        </p>
      </div>
    ),
    arch: {
      intro: (
        <>
          Your question is classified for intent, the flow is scanned for an edge, and the model
          decides between a defined call and NO TRADE — every LIVE call logged to a daily journal that
          caps how many it will make.
        </>
      ),
      nodes: [
        { x: 15, y: 20, label: 'You ask', sub: 'for a call' },
        { x: 195, y: 20, label: 'Intent · LLM', sub: 'classify', accent: true },
        { x: 375, y: 20, label: 'Scan tools', sub: 'OI · structure · mom' },
        { x: 375, y: 110, label: 'Decide · LLM', sub: 'is there an edge?', accent: true },
        { x: 195, y: 110, label: 'Journal', sub: '2 LIVE / day' },
        { x: 15, y: 110, label: 'Call / NO TRADE', sub: 'entry · stop · target' }
      ],
      edges: LOOP_EDGES,
      steps: (
        <ol className={w.steps}>
          <li>
            <strong>You ask</strong> for a read or a setup.
          </li>
          <li>
            <strong>Intent is classified</strong> — a scan, a follow-up, or chatter.
          </li>
          <li>
            <strong>Scan tools</strong> read OI flow, structure and momentum.
          </li>
          <li>
            <strong>The model decides</strong> — a defined call, or NO TRADE.
          </li>
          <li>
            <strong>A LIVE call</strong> comes with entry, stop and target.
          </li>
          <li>
            <strong>The journal</strong> logs it and enforces the daily cap.
          </li>
        </ol>
      )
    }
  },

  hugin: {
    mark: 'H',
    title: 'About HUGIN',
    kicker: 'The market-memory agent — reflect, grade, remember.',
    about: (
      <div className={w.section}>
        <p className={w.lead}>
          HUGIN is an autonomous agent that builds a <strong>memory of the market</strong>. Every hour
          the market is open it records a short read — a bias, an expectation and the key levels — then
          the following hour it grades how right that read turned out and keeps the lesson. Over time
          it learns which of its own reads to trust.
        </p>
        <h3 className={w.h3}>Where it fits</h3>
        <p className={w.p}>
          It is the third of three sibling agents: <strong>HELLA reads</strong> the tape,{' '}
          <strong>STRYX acts</strong> on setups, and <strong>HUGIN remembers</strong> — scoring
          itself so its conviction is earned, not asserted.
        </p>
        <h3 className={w.h3}>Use cases</h3>
        <ul className={w.list}>
          <li>
            <strong>Hourly market read.</strong> A running, timestamped log of what HUGIN expected for
            NIFTY, SENSEX or BANK NIFTY through the session.
          </li>
          <li>
            <strong>Self-graded accuracy.</strong> Each read is marked hit / partial / miss the next
            hour with cited evidence, so you can see how reliable it actually is.
          </li>
          <li>
            <strong>Lessons that compound.</strong> Repeated patterns become lessons with a
            reliability score, sharpening the reads over days.
          </li>
          <li>
            <strong>Calls weighed against its record.</strong> Ask for a call and HUGIN turns its reads
            and lessons into an actionable view — conviction discounted by its measured hit-rate.
          </li>
          <li>
            <strong>Ask its memory.</strong> The Analysis Agent answers questions about the day using
            only what HUGIN has observed and learned.
          </li>
        </ul>
      </div>
    ),
    usage: (
      <div className={w.section}>
        <h3 className={w.h3}>Getting started</h3>
        <ol className={w.steps}>
          <li>
            <strong>Add your LLM key.</strong> HUGIN reflects on your own key — set one in{' '}
            <Link to="/settings/ai">Settings → AI</Link>.
          </li>
          <li>
            <strong>Turn it on.</strong> It is off by default (it spends tokens each hour). Enable it
            in <Link to="/settings/hugin">Settings → HUGIN Automation</Link>.
          </li>
          <li>
            <strong>Pick an instrument.</strong> Use the NIFTY / SENSEX / BANK NIFTY switcher — each
            keeps its own separate memory.
          </li>
        </ol>
        <h3 className={w.h3}>Reading the console</h3>
        <ul className={w.list}>
          <li>
            <strong>AI Dashboard.</strong> The scoreboard shows today&apos;s and all-time hit-rate; the
            hourly timeline lists each read and its grade; lessons and the track record show how it is
            sharpening.
          </li>
          <li>
            <strong>Get a call.</strong> In the Calls panel, generate an actionable call built from
            what HUGIN has learned, with conviction weighed against its track record.
          </li>
          <li>
            <strong>HUGIN Analysis Agent.</strong> Switch to the Agent view and ask about the day —
            e.g. &ldquo;What&apos;s your read on NIFTY?&rdquo; or &ldquo;Have you been right
            today?&rdquo;. It answers only from its own memory.
          </li>
        </ul>
        <p className={w.note}>
          Give it a full session or two — the value comes from the graded history it accumulates.
        </p>
      </div>
    ),
    arch: {
      intro: (
        <>
          An hourly worker snapshots the market, asks the LLM for a read, and the next hour grades the
          previous read against what actually happened — writing observations, grades and lessons into
          HUGIN&apos;s per-user, per-instrument memory that the console reads from.
        </>
      ),
      nodes: [
        { x: 15, y: 20, label: 'Hourly trigger', sub: 'scheduler' },
        { x: 195, y: 20, label: 'Market snapshot', sub: 'price · OI · levels' },
        { x: 375, y: 20, label: 'Reflect · LLM', sub: 'your key', accent: true },
        { x: 375, y: 110, label: 'Grade · LLM judge', sub: 'next hour', accent: true },
        { x: 195, y: 110, label: 'Memory store', sub: 'reads · lessons' },
        { x: 15, y: 110, label: 'Console', sub: 'dash · calls · chat' }
      ],
      edges: LOOP_EDGES,
      steps: (
        <ol className={w.steps}>
          <li>
            <strong>Trigger.</strong> An hourly scheduler fires while the market is open.
          </li>
          <li>
            <strong>Snapshot.</strong> It pulls a market snapshot — price, OI walls and key levels.
          </li>
          <li>
            <strong>Reflect.</strong> Your LLM turns it into an observation: bias, expectation and
            levels.
          </li>
          <li>
            <strong>Grade.</strong> The next hour, an LLM judge scores the earlier read with evidence.
          </li>
          <li>
            <strong>Learn.</strong> Grades roll up into lessons and a daily track-record.
          </li>
          <li>
            <strong>Serve.</strong> The dashboard, calls and chat agent read from this memory.
          </li>
        </ol>
      )
    }
  }
};
