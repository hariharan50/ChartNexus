/**
 * TanStack Query hooks for MME100.
 *
 * Availability and enrollment change only with server config / a toggle, so they
 * use a long stale window and no polling. The morning briefing is written once by
 * the worker; the read polls occasionally so a freshly-generated briefing appears
 * without a reload.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  getMme100Availability,
  getMme100BriefingToday,
  getMme100Enrollment,
  setMme100Enrollment
} from './api';
import type { Mme100Availability, Mme100Briefing, Mme100Enrollment } from './types';

const AVAILABILITY_STALE_MS = 5 * 60_000;
const BRIEFING_REFETCH_MS = 5 * 60_000;

export function useMme100AvailabilityQuery() {
  return useQuery<Mme100Availability>({
    queryKey: ['mme100', 'availability'],
    queryFn: () => getMme100Availability(),
    staleTime: AVAILABILITY_STALE_MS
  });
}

const ENROLLMENT_KEY = ['mme100', 'enrollment'];

export function useMme100EnrollmentQuery() {
  return useQuery<Mme100Enrollment>({
    queryKey: ENROLLMENT_KEY,
    queryFn: () => getMme100Enrollment(),
    staleTime: AVAILABILITY_STALE_MS
  });
}

/** Toggle the briefing on/off; refreshes the cached enrollment so the UI reflects it. */
export function useSetMme100EnrollmentMutation() {
  const queryClient = useQueryClient();
  return useMutation<Mme100Enrollment, Error, boolean>({
    mutationFn: (enabled: boolean) => setMme100Enrollment(enabled),
    onSuccess: (data) => {
      queryClient.setQueryData<Mme100Enrollment>(ENROLLMENT_KEY, data);
    }
  });
}

export function useMme100BriefingTodayQuery() {
  return useQuery<Mme100Briefing | null>({
    queryKey: ['mme100', 'briefing', 'today'],
    queryFn: () => getMme100BriefingToday(),
    refetchInterval: BRIEFING_REFETCH_MS
  });
}
