/**
 * TanStack Query hooks for HUGIN.
 *
 * HUGIN writes memory from its background worker; the UI only reads. Memory polls
 * on a 60s cadence (an hourly agent doesn't change faster than that); availability
 * changes only with server config, so it uses a long stale window and no polling.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  generateHuginCall,
  getHuginAvailability,
  getHuginCalls,
  getHuginEnrollment,
  getHuginHistory,
  getHuginMemoryToday,
  setHuginEnrollment
} from './api';
import type {
  HuginAvailability,
  HuginCall,
  HuginCalls,
  HuginEnrollment,
  HuginHistory,
  HuginMemoryToday
} from './types';

const MEMORY_REFETCH_MS = 60_000;
const AVAILABILITY_STALE_MS = 5 * 60_000;

export function useHuginAvailabilityQuery() {
  return useQuery<HuginAvailability>({
    queryKey: ['hugin', 'availability'],
    queryFn: () => getHuginAvailability(),
    staleTime: AVAILABILITY_STALE_MS
  });
}

const ENROLLMENT_KEY = ['hugin', 'enrollment'];

export function useHuginEnrollmentQuery() {
  return useQuery<HuginEnrollment>({
    queryKey: ENROLLMENT_KEY,
    queryFn: () => getHuginEnrollment(),
    staleTime: AVAILABILITY_STALE_MS
  });
}

/** Toggle HUGIN on/off; refreshes the cached enrollment so the UI reflects it. */
export function useSetHuginEnrollmentMutation() {
  const queryClient = useQueryClient();
  return useMutation<HuginEnrollment, Error, boolean>({
    mutationFn: (enabled: boolean) => setHuginEnrollment(enabled),
    onSuccess: (data) => {
      queryClient.setQueryData<HuginEnrollment>(ENROLLMENT_KEY, data);
    }
  });
}

export function useHuginMemoryTodayQuery(symbol: string) {
  return useQuery<HuginMemoryToday>({
    queryKey: ['hugin', 'memory', symbol],
    queryFn: () => getHuginMemoryToday(symbol),
    refetchInterval: MEMORY_REFETCH_MS
  });
}

export function useHuginHistoryQuery(symbol: string, days = 7) {
  return useQuery<HuginHistory>({
    queryKey: ['hugin', 'history', symbol, days],
    queryFn: () => getHuginHistory(symbol, days),
    refetchInterval: MEMORY_REFETCH_MS
  });
}

export function useHuginCallsQuery(symbol: string) {
  return useQuery<HuginCalls>({
    queryKey: ['hugin', 'calls', symbol],
    queryFn: () => getHuginCalls(symbol)
  });
}

/** Generate a new call, then refresh the recent-calls list. */
export function useGenerateHuginCallMutation(symbol: string) {
  const queryClient = useQueryClient();
  return useMutation<HuginCall, Error, void>({
    mutationFn: () => generateHuginCall(symbol),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['hugin', 'calls', symbol] });
    }
  });
}
