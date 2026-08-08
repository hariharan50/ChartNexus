import { useState } from 'react';
import { useAskAgentMutation } from '$contexts/signals/queries';
import type { ChatMessage } from '$contexts/signals/types';
import { cx } from '$shared/ui/cx';
import { INSTRUMENTS, SUGGESTIONS, nextId } from '../ai-console-data';
import ConsoleHeader from '../components/ConsoleHeader';
import s from './route.module.css';
import type { Route } from './+types/route';

export const meta: Route.MetaFunction = () => [
  { title: 'Hella · AI Analysis Agent · MarketCompass' }
];

/** The agent's name, shown throughout the console. */
const AGENT_NAME = 'Hella';

export default function AiAnalysisAgent() {
  const [instIdx, setInstIdx] = useState(0);
  const instrument = INSTRUMENTS[instIdx] ?? INSTRUMENTS[0];

  return (
    <div className={s.page}>
      <ConsoleHeader
        title="AI Analysis Agent"
        subtitle={
          <>
            Ask <strong>{AGENT_NAME}</strong> — your soft-spoken guide over OI, price action, levels
            and risk.
          </>
        }
        instIdx={instIdx}
        onSelect={setInstIdx}
      />

      <div className={s.wrap}>
        <ChatPanel symbol={instrument.symbol} />
      </div>
    </div>
  );
}

function ChatPanel({ symbol }: { symbol: string }) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const ask = useAskAgentMutation(symbol);

  async function submit(question: string) {
    const trimmed = question.trim();
    if (!trimmed || ask.isPending) return;
    setInput('');
    setMessages((prev) => [...prev, { id: nextId(), role: 'user', text: trimmed }]);
    try {
      const answer = await ask.mutateAsync(trimmed);
      setMessages((prev) => [
        ...prev,
        { id: nextId(), role: 'agent', text: answer.answer, source: answer.source }
      ]);
    } catch {
      setMessages((prev) => [
        ...prev,
        { id: nextId(), role: 'agent', text: 'Sorry — I could not answer that just now.' }
      ]);
    }
  }

  return (
    <div className={cx(s.panel, s.chat)}>
      <div className={s.chatHead}>
        <span className={s.avatar}>H</span>
        <div>
          <div className={s.chatName}>{AGENT_NAME}</div>
          <div className={s.chatSub}>Soft-spoken guide · {symbol}</div>
        </div>
      </div>

      <div className={s.messages}>
        {messages.length === 0 ? (
          <p className={s.empty}>
            Hi, I&apos;m {AGENT_NAME}. Ask me about the call, your stop, the target, or which levels
            matter for {symbol} — I&apos;ll walk you through it gently.
          </p>
        ) : (
          messages.map((msg) => (
            <div key={msg.id} className={cx(s.bubble, s[msg.role])}>
              {msg.role === 'agent' ? <div className={s.author}>{AGENT_NAME}</div> : null}
              <div className={s.bubbleText}>{msg.text}</div>
              {msg.role === 'agent' && msg.source && msg.source !== 'rule_based' ? (
                <div className={s.msgMeta}>via {msg.source}</div>
              ) : null}
            </div>
          ))
        )}
        {ask.isPending ? (
          <div className={cx(s.bubble, s.agent, s.thinking)}>{AGENT_NAME} is thinking…</div>
        ) : null}
      </div>

      <div className={s.suggestions}>
        {SUGGESTIONS.map((suggestion) => (
          <button
            key={suggestion}
            type="button"
            className={s.suggestion}
            onClick={() => void submit(suggestion)}
          >
            {suggestion}
          </button>
        ))}
      </div>

      <form
        className={s.composer}
        onSubmit={(event) => {
          event.preventDefault();
          void submit(input);
        }}
      >
        <input
          className={s.input}
          value={input}
          onChange={(event) => setInput(event.target.value)}
          placeholder={`Ask ${AGENT_NAME}…`}
          aria-label={`Ask ${AGENT_NAME}`}
          maxLength={500}
        />
        <button type="submit" className={s.send} disabled={ask.isPending || !input.trim()}>
          Send
        </button>
      </form>
    </div>
  );
}
