import { useRef, useState } from 'react';
import { Link } from 'react-router';
import { streamHuginChat } from '$contexts/hugin/api';
import {
  useGenerateHuginCallMutation,
  useHuginAvailabilityQuery,
  useHuginCallsQuery,
  useHuginEnrollmentQuery,
  useHuginHistoryQuery,
  useHuginMemoryTodayQuery
} from '$contexts/hugin/queries';
import type { HuginCall, HuginDay, HuginLesson, HuginObservation } from '$contexts/hugin/types';
import { cx } from '$shared/ui/cx';
import { INSTRUMENTS } from '../ai-console-data';
import AgentInfoWindow from '../components/AgentInfoWindow';
import ConsoleHeader from '../components/ConsoleHeader';
import s from './route.module.css';
import type { Route } from './+types/route';

export const meta: Route.MetaFunction = () => [{ title: 'HUGIN · Market Memory · MarketCompass' }];

const AGENT_NAME = 'HUGIN';

type HuginView = 'dashboard' | 'agent' | 'calls';

export default function HuginConsole() {
  const [instIdx, setInstIdx] = useState(0);
  const [view, setView] = useState<HuginView>('dashboard');
  const [infoOpen, setInfoOpen] = useState(false);
  const instrument = INSTRUMENTS[instIdx] ?? INSTRUMENTS[0];
  const availability = useHuginAvailabilityQuery();
  const enrollment = useHuginEnrollmentQuery();
  // HUGIN reflects on the tenant owner's LLM key; with none, it produces no
  // memory. And it is off by default — it only runs once turned on in Settings.
  const noKey = availability.data?.available === false;
  const off = enrollment.data?.enabled === false;

  const viewButtons = (
    <div className={s.viewTabs} role="tablist" aria-label="HUGIN view">
      <button
        type="button"
        role="tab"
        aria-selected={view === 'agent'}
        className={cx(s.viewTab, view === 'agent' && s.viewActive)}
        onClick={() => setView('agent')}
      >
        HUGIN Analysis Agent
      </button>
      <button
        type="button"
        role="tab"
        aria-selected={view === 'dashboard'}
        className={cx(s.viewTab, view === 'dashboard' && s.viewActive)}
        onClick={() => setView('dashboard')}
      >
        AI Dashboard
      </button>
      <button
        type="button"
        role="tab"
        aria-selected={view === 'calls'}
        className={cx(s.viewTab, view === 'calls' && s.viewActive)}
        onClick={() => setView('calls')}
      >
        HUGIN Calls
      </button>
    </div>
  );

  return (
    <div className={s.page}>
      <ConsoleHeader
        title="HUGIN · Market Memory"
        mark="H"
        subtitle={
          <>
            <strong>{AGENT_NAME}</strong> watches the market every hour, grades how right its last
            read was, and learns from the miss. HELLA reads, STRYX acts, HUGIN remembers.
          </>
        }
        instIdx={instIdx}
        onSelect={setInstIdx}
        views={viewButtons}
        onInfo={() => setInfoOpen(true)}
      />

      {infoOpen ? <AgentInfoWindow agent="hugin" onClose={() => setInfoOpen(false)} /> : null}

      <div className={s.wrap}>
        {noKey ? (
          <div className={cx(s.panel, s.notice)}>
            <div className={s.noticeTitle}>{AGENT_NAME} is offline</div>
            <p className={s.noticeBody}>
              HUGIN runs on your own LLM key. Add one in{' '}
              <Link to="/settings/ai">Settings → AI</Link>, then reload.
            </p>
          </div>
        ) : off ? (
          <div className={cx(s.panel, s.notice)}>
            <div className={s.noticeTitle}>{AGENT_NAME} is turned off</div>
            <p className={s.noticeBody}>
              HUGIN is off by default because it uses your AI tokens every hour. Turn it on in{' '}
              <Link to="/settings/hugin">Settings → HUGIN Automation</Link> to start building the
              hourly memory.
            </p>
          </div>
        ) : view === 'agent' ? (
          <AgentPanel key={instrument.symbol} symbol={instrument.symbol} />
        ) : view === 'calls' ? (
          <CallsPanel key={instrument.symbol} symbol={instrument.symbol} />
        ) : (
          <DashboardPanel key={instrument.symbol} symbol={instrument.symbol} />
        )}
      </div>
    </div>
  );
}

function DashboardPanel({ symbol }: { symbol: string }) {
  const memory = useHuginMemoryTodayQuery(symbol);
  const history = useHuginHistoryQuery(symbol);
  const data = memory.data;
  const observations = data?.observations ?? [];
  const lessons = data?.lessons ?? [];
  const days = history.data?.days ?? [];

  return (
    <div className={s.grid}>
      <Scoreboard
        hitRate={data?.hit_rate ?? null}
        graded={data?.graded_count ?? 0}
        hits={data?.hit_count ?? 0}
        overall={history.data?.overall_hit_rate ?? null}
      />

      <section className={cx(s.panel, s.timelinePanel)}>
        <h2 className={s.h2}>Hourly timeline · {symbol}</h2>
        {memory.isLoading ? (
          <p className={s.empty}>Loading HUGIN&apos;s memory…</p>
        ) : observations.length === 0 ? (
          <p className={s.empty}>
            No reads yet today. HUGIN records one each hour the market is open, then grades it the
            following hour.
          </p>
        ) : (
          <ol className={s.timeline}>
            {[...observations].reverse().map((obs, idx) => (
              <TimelineCard key={`${obs.tick_at}-${idx}`} obs={obs} />
            ))}
          </ol>
        )}
      </section>

      <section className={cx(s.panel, s.lessonsPanel)}>
        <h2 className={s.h2}>Lessons learned</h2>
        {lessons.length === 0 ? (
          <p className={s.empty}>No lessons yet — they accrue as HUGIN grades its own reads.</p>
        ) : (
          <ul className={s.lessons}>
            {lessons.map((lesson, idx) => (
              <LessonRow key={`${lesson.text}-${idx}`} lesson={lesson} />
            ))}
          </ul>
        )}
      </section>

      <section className={cx(s.panel, s.trackPanel)}>
        <h2 className={s.h2}>Track record · how HUGIN is sharpening</h2>
        {days.length === 0 ? (
          <p className={s.empty}>
            No days recorded yet. Each trading day HUGIN runs adds a row here, so you can watch its
            hit-rate improve over time.
          </p>
        ) : (
          <ul className={s.days}>
            {days.map((day) => (
              <DayRow key={day.trading_day} day={day} />
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function CallsPanel({ symbol }: { symbol: string }) {
  const calls = useHuginCallsQuery(symbol);
  const generate = useGenerateHuginCallMutation(symbol);
  const rows = calls.data?.calls ?? [];

  return (
    <section className={cx(s.panel, s.callsPanel)}>
      <div className={s.callsHead}>
        <h2 className={s.h2}>Calls · from what HUGIN has learned</h2>
        <button
          type="button"
          className={s.getCall}
          disabled={generate.isPending}
          onClick={() => generate.mutate()}
        >
          {generate.isPending ? 'Thinking…' : 'Get a call'}
        </button>
      </div>
      {generate.isError ? (
        <p className={s.empty}>Couldn’t generate a call just now — try again.</p>
      ) : null}
      {rows.length === 0 ? (
        <p className={s.empty}>
          No calls yet. Click <strong>Get a call</strong> and HUGIN will turn its reads and lessons
          into an actionable call — with a conviction weighed against its own track record.
        </p>
      ) : (
        <ul className={s.calls}>
          {rows.map((call, idx) => (
            <CallCard key={`${call.created_at}-${idx}`} call={call} />
          ))}
        </ul>
      )}
    </section>
  );
}

function AgentPanel({ symbol }: { symbol: string }) {
  return (
    <section className={cx(s.panel, s.agentPanel)}>
      <div className={s.chatHead}>
        <span className={s.avatar}>H</span>
        <div>
          <div className={s.chatName}>{AGENT_NAME}</div>
          <div className={s.chatSub}>Market memory · {symbol}</div>
        </div>
      </div>
      <ChatBody symbol={symbol} />
    </section>
  );
}

function CallCard({ call }: { call: HuginCall }) {
  const bias = call.bias.toLowerCase();
  const conviction = Math.round(call.conviction * 100);
  const track = call.track_hit_rate == null ? null : Math.round(call.track_hit_rate * 100);
  return (
    <li className={s.call}>
      <div className={s.cardHead}>
        {call.created_at ? <span className={s.time}>{formatTime(call.created_at)}</span> : null}
        <span className={cx(s.bias, s[`bias_${bias}`])}>{call.bias}</span>
        <span className={s.callTarget}>{call.target_zone}</span>
        <span className={s.conviction} title="Model conviction vs HUGIN's measured hit-rate">
          {conviction}% conviction
          {track == null ? '' : ` · ${track}% track`}
        </span>
      </div>
      {call.entry || call.stop || call.target1 ? (
        <div className={s.levels}>
          <TextLevel label="Entry" value={call.entry} />
          <TextLevel label="Stop" value={call.stop} />
          <TextLevel label="Target 1" value={call.target1} />
          {call.target2 ? <TextLevel label="Target 2" value={call.target2} /> : null}
        </div>
      ) : null}
      <p className={s.evidence}>{call.rationale}</p>
    </li>
  );
}

type ChatMsg = { id: string; role: 'user' | 'hugin'; text: string; streaming?: boolean };

function ChatBody({ symbol }: { symbol: string }) {
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const sessionRef = useRef<string | null>(null);

  function patch(id: string, change: (m: ChatMsg) => ChatMsg) {
    setMessages((prev) => prev.map((m) => (m.id === id ? change(m) : m)));
  }

  async function submit(question: string) {
    const trimmed = question.trim();
    if (!trimmed || busy) return;
    setInput('');
    setBusy(true);
    const id = `${Date.now()}-h`;
    setMessages((prev) => [
      ...prev,
      { id: `${Date.now()}-u`, role: 'user', text: trimmed },
      { id, role: 'hugin', text: '', streaming: true }
    ]);
    try {
      await streamHuginChat(symbol, trimmed, sessionRef.current, (event) => {
        if (event.type === 'session') sessionRef.current = event.session_id;
        else if (event.type === 'token') patch(id, (m) => ({ ...m, text: m.text + event.text }));
        else if (event.type === 'error')
          patch(id, (m) => ({ ...m, text: m.text || event.message, streaming: false }));
      });
    } catch {
      patch(id, (m) => ({ ...m, text: m.text || 'Couldn’t answer just now — try again.' }));
    } finally {
      patch(id, (m) => (m.streaming ? { ...m, streaming: false } : m));
      setBusy(false);
    }
  }

  return (
    <div className={s.modeBody}>
      <div className={s.chatLog}>
        {messages.length === 0 ? (
          <p className={s.empty}>
            Ask about the day so far — e.g. “What’s your read on {symbol}?”, “Have you been right
            today?”, or “What have you learned?”. HUGIN answers only from its own memory.
          </p>
        ) : (
          messages.map((m) => (
            <div
              key={m.id}
              className={cx(s.chatBubble, m.role === 'user' ? s.chatUser : s.chatHugin)}
            >
              {m.role === 'hugin' ? <span className={s.chatWho}>HUGIN</span> : null}
              <span className={s.chatText}>
                {m.text || (m.streaming ? 'Thinking…' : '')}
                {m.streaming && m.text ? <span className={s.caret} aria-hidden="true" /> : null}
              </span>
            </div>
          ))
        )}
      </div>
      <form
        className={s.chatForm}
        onSubmit={(e) => {
          e.preventDefault();
          void submit(input);
        }}
      >
        <input
          className={s.chatInput}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask HUGIN about its reads and lessons…"
          aria-label="Ask HUGIN"
          maxLength={500}
        />
        <button type="submit" className={s.chatSend} disabled={busy || !input.trim()}>
          Send
        </button>
      </form>
    </div>
  );
}

function DayRow({ day }: { day: HuginDay }) {
  const pct = day.hit_rate == null ? null : Math.round(day.hit_rate * 100);
  return (
    <li className={s.day}>
      <span className={s.dayDate}>{formatDay(day.trading_day)}</span>
      <span className={s.dayBar}>
        <span
          className={s.dayFill}
          style={{ width: pct == null ? '0%' : `${pct}%` }}
          data-empty={pct == null}
        />
      </span>
      <span className={s.dayPct}>{pct == null ? '—' : `${pct}%`}</span>
      <span className={s.dayTally}>
        {day.graded_count === 0 ? 'ungraded' : `${day.hit_count}/${day.graded_count}`}
      </span>
    </li>
  );
}

function Scoreboard({
  hitRate,
  graded,
  hits,
  overall
}: {
  hitRate: number | null;
  graded: number;
  hits: number;
  overall: number | null;
}) {
  const pct = hitRate == null ? '—' : `${Math.round(hitRate * 100)}%`;
  const overallPct = overall == null ? '—' : `${Math.round(overall * 100)}%`;
  return (
    <section className={cx(s.panel, s.scoreboard)}>
      <div className={s.score}>
        <span className={s.scoreValue}>{pct}</span>
        <span className={s.scoreLabel}>hit rate today</span>
      </div>
      <div className={s.score}>
        <span className={cx(s.scoreValue, s.scoreValueMuted)}>{overallPct}</span>
        <span className={s.scoreLabel}>all-time hit rate</span>
      </div>
      <div className={s.scoreMeta}>
        {graded === 0
          ? 'Nothing graded yet today'
          : `${hits} of ${graded} graded read${graded === 1 ? '' : 's'} hit today`}
      </div>
    </section>
  );
}

function TimelineCard({ obs }: { obs: HuginObservation }) {
  const bias = obs.bias.toLowerCase();
  const grade = obs.grade?.toLowerCase() ?? null;
  const evidenceNote = obs.grade_evidence?.note ?? '';
  return (
    <li className={s.card}>
      <div className={s.cardHead}>
        <span className={s.time}>{formatTime(obs.tick_at)}</span>
        <span className={cx(s.bias, s[`bias_${bias}`])}>{obs.bias}</span>
        {grade ? (
          <span className={cx(s.grade, s[`grade_${grade}`])} title={evidenceNote || undefined}>
            {obs.grade}
          </span>
        ) : (
          <span className={cx(s.grade, s.gradePending)} title="Graded next hour">
            pending
          </span>
        )}
      </div>
      <p className={s.expectation}>{obs.expectation}</p>
      <div className={s.levels}>
        <Level label="Call wall" value={obs.call_wall} />
        <Level label="Put wall" value={obs.put_wall} />
        <Level label="Key level" value={obs.key_level} />
      </div>
      {grade && (evidenceNote || obs.grade_evidence?.actual_move) ? (
        <p className={s.evidence}>
          {obs.grade_evidence?.actual_move ? <>Actual: {obs.grade_evidence.actual_move}. </> : null}
          {evidenceNote}
        </p>
      ) : null}
    </li>
  );
}

function Level({ label, value }: { label: string; value: number | null }) {
  return (
    <span className={s.level}>
      <span className={s.levelLabel}>{label}</span>
      <span className={s.levelValue}>{value == null ? '—' : value.toLocaleString('en-IN')}</span>
    </span>
  );
}

function TextLevel({ label, value }: { label: string; value: string | null }) {
  return (
    <span className={s.level}>
      <span className={s.levelLabel}>{label}</span>
      <span className={s.levelValue}>{value ?? '—'}</span>
    </span>
  );
}

function LessonRow({ lesson }: { lesson: HuginLesson }) {
  const pct = Math.round(lesson.reliability * 100);
  return (
    <li className={s.lesson}>
      <p className={s.lessonText}>{lesson.text}</p>
      <div className={s.lessonMeta}>
        <span className={s.reliability} title="Reliability (Laplace-smoothed hit rate)">
          <span className={s.reliabilityBar}>
            <span className={s.reliabilityFill} style={{ width: `${pct}%` }} />
          </span>
          {pct}%
        </span>
        <span className={s.tally}>
          {lesson.hits}✓ · {lesson.misses}✗
        </span>
      </div>
    </li>
  );
}

/** "Mon 21 Aug" for a trading-day date string. */
function formatDay(day: string): string {
  try {
    return new Intl.DateTimeFormat('en-IN', {
      weekday: 'short',
      day: '2-digit',
      month: 'short',
      timeZone: 'Asia/Kolkata'
    }).format(new Date(`${day}T00:00:00+05:30`));
  } catch {
    return day;
  }
}

/** HH:MM in IST — HUGIN's ticks are session-aligned, so the clock reads naturally. */
function formatTime(iso: string): string {
  try {
    return new Intl.DateTimeFormat('en-IN', {
      hour: '2-digit',
      minute: '2-digit',
      timeZone: 'Asia/Kolkata'
    }).format(new Date(iso));
  } catch {
    return iso;
  }
}
