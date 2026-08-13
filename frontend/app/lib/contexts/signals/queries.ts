/**
 * TanStack Query hooks for the AI Market Guider.
 *
 * Guidance polls on the same ~15s cadence as the rest of the terminal; the chat
 * is a mutation (one request per question), not a polled query.
 */

import { useMutation, useQuery } from '@tanstack/react-query';
import { queryKeys } from '$shared/api/query-client';
import { askAgent, getAgentAvailability, getGuidance } from './api';
import type { AgentAvailability, AskResponse, Guidance } from './types';

const REFETCH_MS = 15_000;
// Availability only changes with server config (an LLM key), so a long stale
// window is fine — no polling.
const AVAILABILITY_STALE_MS = 5 * 60_000;

export function useGuidanceQuery(symbol: string) {
  return useQuery<Guidance>({
    queryKey: queryKeys.signals({ symbol }),
    queryFn: () => getGuidance(symbol),
    refetchInterval: REFETCH_MS
  });
}

export function useAskAgentMutation(symbol: string) {
  return useMutation<AskResponse, Error, string>({
    mutationFn: (question: string) => askAgent(symbol, question)
  });
}

export function useAgentAvailabilityQuery() {
  return useQuery<AgentAvailability>({
    queryKey: ['copilot', 'availability'],
    queryFn: () => getAgentAvailability(),
    staleTime: AVAILABILITY_STALE_MS
  });
}
