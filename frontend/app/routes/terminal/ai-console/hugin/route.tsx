import { useEffect, useRef, useState } from 'react';
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
              <Link to="/settings/power-agents">Settings → Power AI Agents</Link> to start building
              the hourly memory.
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

/** HUGIN's history over a wide window, so "all-time" and "days tracked" mean
 *  something rather than reflecting only the last week. */
const HISTORY_WINDOW_DAYS = 90;

function pctText(v: number | null | undefined): string {
  return v == null ? '—' : `${Math.round(v * 100)}%`;
}

function DashboardPanel({ symbol }: { symbol: string }) {
  const memory = useHuginMemoryTodayQuery(symbol);
  const history = useHuginHistoryQuery(symbol, HISTORY_WINDOW_DAYS);
  const data = memory.data;
  const observations = data?.observations ?? [];
  const lessons = data?.lessons ?? [];
  const days = history.data?.days ?? [];

  const hitToday = data?.hit_rate ?? null;
  const gradedToday = data?.graded_count ?? 0;
  const hitsToday = data?.hit_count ?? 0;
  const overall = history.data?.overall_hit_rate ?? null;
  const overallGraded = history.data?.overall_graded ?? 0;

  // Derived insights — everything below is aggregated client-side from the two
  // queries above; there is no dedicated stats endpoint.
  const daysTracked = days.filter((d) => d.graded_count > 0).length;
  const avgReliability = lessons.length
    ? lessons.reduce((sum, l) => sum + l.reliability, 0) / lessons.length
    : null;
  const grades = countGrades(observations);
  const biases = countBiases(observations);
  const trend = dayTrend(days);

  return (
    <div className={s.dash}>
      {/* Insight strip — the whole picture at a glance. */}
      <section className={s.kpiRow} aria-label="HUGIN at a glance">
        <KpiTile
          label="Hit rate today"
          value={pctText(hitToday)}
          sub={gradedSub(hitsToday, gradedToday)}
          tone="accent"
        />
        <KpiTile
          label="All-time hit rate"
          value={pctText(overall)}
          sub={`${history.data?.overall_hits ?? 0}/${overallGraded} graded`}
          tone="mint"
        />
        <KpiTile
          label="Reads today"
          value={String(observations.length)}
          sub={`${gradedToday} graded`}
        />
        <KpiTile
          label="Lessons learned"
          value={String(lessons.length)}
          sub={avgReliability == null ? 'none yet' : `${pctText(avgReliability)} avg reliability`}
        />
        <KpiTile
          label="Days tracked"
          value={String(daysTracked)}
          sub={`over ${HISTORY_WINDOW_DAYS} days`}
        />
        <KpiTile label="Reads graded" value={String(overallGraded)} sub="all-time" />
      </section>

      {/* Accuracy hero. */}
      <section className={cx(s.panel, s.heroPanel)} aria-label="Accuracy">
        <RingGauge today={hitToday} overall={overall} />
        <div className={s.heroBody}>
          <p className={s.statusLine}>{statusText(hitToday, overall, hitsToday, gradedToday)}</p>
          <div className={s.heroStats}>
            <HeroStat swatch="accent" label="hit rate today" value={pctText(hitToday)} />
            <HeroStat swatch="mint" label="all-time hit rate" value={pctText(overall)} />
            <HeroStat swatch="amber" label="reads graded" value={`${hitsToday}/${gradedToday}`} />
          </div>
        </div>
      </section>

      {/* Insight grid. */}
      <div className={s.insightCols}>
        <div className={s.colMain}>
          <section className={cx(s.panel, s.timelinePanel)}>
            <h2 className={s.h2}>Hourly timeline · {symbol}</h2>
            {memory.isLoading ? (
              <p className={s.empty}>Loading HUGIN&apos;s memory…</p>
            ) : observations.length === 0 ? (
              <p className={s.empty}>
                No reads yet today. HUGIN records one each hour the market is open, then grades it
                the following hour.
              </p>
            ) : (
              <ol className={s.timeline}>
                {[...observations].reverse().map((obs, idx) => (
                  <TimelineCard key={`${obs.tick_at}-${idx}`} obs={obs} />
                ))}
              </ol>
            )}
          </section>

          <div className={s.miniRow}>
            <section className={cx(s.panel, s.miniPanel)}>
              <h2 className={s.h2}>Grade breakdown · today</h2>
              {gradedToday === 0 && grades.pending === 0 ? (
                <p className={s.empty}>
                  Nothing graded yet. Each read is scored the following hour.
                </p>
              ) : (
                <SegBar
                  segments={[
                    { key: 'hit', label: 'Hit', value: grades.hit, cls: s.segHit },
                    { key: 'partial', label: 'Partial', value: grades.partial, cls: s.segPartial },
                    { key: 'miss', label: 'Miss', value: grades.miss, cls: s.segMiss },
                    { key: 'pending', label: 'Pending', value: grades.pending, cls: s.segPending }
                  ]}
                />
              )}
            </section>

            <section className={cx(s.panel, s.miniPanel)}>
              <h2 className={s.h2}>Bias mix · today</h2>
              {observations.length === 0 ? (
                <p className={s.empty}>No reads yet — the mix appears once HUGIN starts logging.</p>
              ) : (
                <SegBar
                  segments={[
                    { key: 'bullish', label: 'Bullish', value: biases.bullish, cls: s.segHit },
                    { key: 'bearish', label: 'Bearish', value: biases.bearish, cls: s.segMiss },
                    { key: 'neutral', label: 'Neutral', value: biases.neutral, cls: s.segPartial }
                  ]}
                />
              )}
            </section>
          </div>
        </div>

        <div className={s.colSide}>
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
            <div className={s.trackHead}>
              <h2 className={s.h2}>Track record · how HUGIN is sharpening</h2>
              {trend ? <TrendChip trend={trend} /> : null}
            </div>
            {days.length === 0 ? (
              <p className={s.empty}>
                No days recorded yet. Each trading day HUGIN runs adds a row here, so you can watch
                its hit-rate improve over time.
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
      </div>
    </div>
  );
}

function gradedSub(hits: number, graded: number): string {
  return graded === 0 ? 'none graded yet' : `${hits}/${graded} hit`;
}

function statusText(
  hitToday: number | null,
  overall: number | null,
  hits: number,
  graded: number
): string {
  if (graded === 0) {
    return 'Nothing graded yet today. HUGIN logs a read each hour the market is open and grades it the following hour.';
  }
  const plural = graded === 1 ? '' : 's';
  if (hitToday != null && overall != null) {
    const rel = hitToday >= overall ? 'tracking above' : 'tracking below';
    return `${hits} of ${graded} graded read${plural} hit today — ${rel} HUGIN's all-time line.`;
  }
  return `${hits} of ${graded} graded read${plural} hit today.`;
}

type GradeCounts = { hit: number; partial: number; miss: number; pending: number };
function countGrades(observations: HuginObservation[]): GradeCounts {
  const c: GradeCounts = { hit: 0, partial: 0, miss: 0, pending: 0 };
  for (const o of observations) {
    const g = o.grade?.toLowerCase() ?? null;
    if (g === 'hit') c.hit += 1;
    else if (g === 'partial') c.partial += 1;
    else if (g === 'miss') c.miss += 1;
    else c.pending += 1;
  }
  return c;
}

type BiasCounts = { bullish: number; bearish: number; neutral: number };
function countBiases(observations: HuginObservation[]): BiasCounts {
  const c: BiasCounts = { bullish: 0, bearish: 0, neutral: 0 };
  for (const o of observations) {
    const b = o.bias.toLowerCase();
    if (b.includes('bull')) c.bullish += 1;
    else if (b.includes('bear')) c.bearish += 1;
    else c.neutral += 1;
  }
  return c;
}

type Trend = 'up' | 'down' | 'flat';
/** Compare the most recent graded days against the ones before them. Returns
 *  null until there are enough graded days on both sides to compare. */
function dayTrend(days: HuginDay[]): Trend | null {
  const graded = days.filter((d) => d.hit_rate != null); // already newest-first
  if (graded.length < 4) return null;
  const half = Math.min(3, Math.floor(graded.length / 2));
  const recent = graded.slice(0, half);
  const prior = graded.slice(half, half * 2);
  const avg = (xs: HuginDay[]) => xs.reduce((s, d) => s + (d.hit_rate ?? 0), 0) / xs.length;
  const delta = avg(recent) - avg(prior);
  if (delta > 0.05) return 'up';
  if (delta < -0.05) return 'down';
  return 'flat';
}

function KpiTile({
  label,
  value,
  sub,
  tone
}: {
  label: string;
  value: string;
  sub: string;
  tone?: 'accent' | 'mint';
}) {
  return (
    <div className={s.kpi}>
      <span className={s.kpiLabel}>
        {tone ? <span className={cx(s.kpiDot, tone === 'mint' ? s.dotMint : s.dotAccent)} /> : null}
        {label}
      </span>
      <span
        className={cx(s.kpiValue, tone === 'accent' && s.kpiAccent, tone === 'mint' && s.kpiMint)}
      >
        {value}
      </span>
      <span className={s.kpiSub}>{sub}</span>
    </div>
  );
}

function HeroStat({
  swatch,
  label,
  value
}: {
  swatch: 'accent' | 'mint' | 'amber';
  label: string;
  value: string;
}) {
  const dot = swatch === 'mint' ? s.dotMint : swatch === 'amber' ? s.dotAmber : s.dotAccent;
  return (
    <div className={s.heroStat}>
      <span className={s.heroStatKey}>
        <span className={cx(s.kpiDot, dot)} />
        {label}
      </span>
      <span className={s.heroStatValue}>{value}</span>
    </div>
  );
}

/** A ring gauge: today's hit-rate as the thick accent arc, all-time as a thin
 *  inner track. Animates in on mount; the CSS transition is dropped under
 *  prefers-reduced-motion. */
function RingGauge({ today, overall }: { today: number | null; overall: number | null }) {
  const [mounted, setMounted] = useState(false);
  useEffect(() => {
    const id = requestAnimationFrame(() => setMounted(true));
    return () => cancelAnimationFrame(id);
  }, []);
  const arcOffset = mounted ? 100 - Math.round((today ?? 0) * 100) : 100;
  const innerOffset = mounted ? 100 - Math.round((overall ?? 0) * 100) : 100;
  return (
    <div className={s.gauge}>
      <svg viewBox="0 0 148 148" aria-hidden="true" className={s.gaugeSvg}>
        <circle className={s.gaugeTrack} cx="74" cy="74" r="62" strokeWidth="12" />
        <circle
          className={s.gaugeArc}
          cx="74"
          cy="74"
          r="62"
          strokeWidth="12"
          pathLength={100}
          style={{ strokeDashoffset: arcOffset }}
        />
        <circle className={s.gaugeTrackInner} cx="74" cy="74" r="44" strokeWidth="3" />
        <circle
          className={s.gaugeArcInner}
          cx="74"
          cy="74"
          r="44"
          strokeWidth="3"
          pathLength={100}
          style={{ strokeDashoffset: innerOffset }}
        />
      </svg>
      <div className={s.gaugeCenter}>
        <span className={s.gaugePct}>{pctText(today)}</span>
        <span className={s.gaugeCaption}>hit rate today</span>
      </div>
    </div>
  );
}

type Seg = { key: string; label: string; value: number; cls: string | undefined };
/** A stacked proportional bar with a small legend — used for grade and bias mix. */
function SegBar({ segments }: { segments: Seg[] }) {
  const total = segments.reduce((sum, seg) => sum + seg.value, 0);
  return (
    <div className={s.seg}>
      <div className={s.segBar}>
        {total === 0
          ? null
          : segments
              .filter((seg) => seg.value > 0)
              .map((seg) => (
                <span
                  key={seg.key}
                  className={cx(s.segFill, seg.cls)}
                  style={{ width: `${(seg.value / total) * 100}%` }}
                  title={`${seg.label}: ${seg.value}`}
                />
              ))}
      </div>
      <ul className={s.segLegend}>
        {segments.map((seg) => (
          <li key={seg.key} className={s.segLegendItem}>
            <span className={cx(s.segSwatch, seg.cls)} />
            {seg.label}
            <span className={s.segCount}>{seg.value}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function TrendChip({ trend }: { trend: Trend }) {
  const meta =
    trend === 'up'
      ? { cls: s.trendUp, text: 'Sharpening', arrow: '↑' }
      : trend === 'down'
        ? { cls: s.trendDown, text: 'Cooling', arrow: '↓' }
        : { cls: s.trendFlat, text: 'Steady', arrow: '→' };
  return (
    <span className={cx(s.trendChip, meta.cls)} title="Recent days vs. the days before">
      {meta.arrow} {meta.text}
    </span>
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
