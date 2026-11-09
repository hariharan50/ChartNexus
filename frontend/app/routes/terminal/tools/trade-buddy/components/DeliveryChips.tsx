import { cx } from '$shared/ui/cx';
import {
  channelStep,
  type AlertChannelView,
  type EngineState,
  type ChannelStep
} from '../trade-buddy-data';
import s from './DeliveryChips.module.css';

/**
 * Will an alert actually reach me, and is there any WhatsApp budget left?
 *
 * Up here beside the instrument tabs because both are preconditions for
 * everything below: a page full of live levels and a disconnected bot is a
 * page that will stay quiet all day and look like it is working. The Delivery
 * card carries the whole setup flow — this is only the answer.
 *
 * Both chips name their state in words. A green dot alone would make "ready"
 * and "paused" the same chip in greyscale, and paused is the state most likely
 * to be mistaken for a fault.
 */
interface Props {
  telegram: AlertChannelView | undefined;
  state: EngineState | undefined;
  /** Scrolls to / focuses the Delivery card. */
  onOpenDelivery?: (() => void) | undefined;
}

const TONE: Record<ChannelStep, 'ok' | 'warn' | 'off'> = {
  ready: 'ok',
  'needs-chat': 'warn',
  paused: 'warn',
  disconnected: 'off'
};

const COPY: Record<ChannelStep, string> = {
  ready: 'Telegram ready',
  'needs-chat': 'Telegram needs a chat',
  paused: 'Telegram paused',
  disconnected: 'Telegram not set up'
};

export default function DeliveryChips({ telegram, state, onOpenDelivery }: Props) {
  const step = channelStep(telegram);
  const tone = TONE[step];

  return (
    <>
      <button
        type="button"
        className={cx(s.chip, s[`tone_${tone}`], s.action)}
        onClick={onOpenDelivery}
      >
        <span className={s.dot} aria-hidden="true" />
        {COPY[step]}
      </button>

      {state ? (
        <span className={s.chip} title="Rolling four-hour window">
          WhatsApp{' '}
          <span className={s.numeric}>
            {state.whatsapp_used}/{state.whatsapp_limit}
          </span>
          <span className={s.muted}> · 4h</span>
        </span>
      ) : null}
    </>
  );
}
