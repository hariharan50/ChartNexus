/** TanStack Query hooks for the daily report (availability + scheduled opt-in). */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getReportAvailability, getReportEnrollment, setReportEnrollment } from './api';
import type { ReportAvailability, ReportEnrollment } from './types';

const AVAILABILITY_STALE_MS = 5 * 60_000;
const ENROLLMENT_KEY = ['report', 'enrollment'];

export function useReportAvailabilityQuery() {
  return useQuery<ReportAvailability>({
    queryKey: ['report', 'availability'],
    queryFn: () => getReportAvailability(),
    staleTime: AVAILABILITY_STALE_MS
  });
}

export function useReportEnrollmentQuery() {
  return useQuery<ReportEnrollment>({
    queryKey: ENROLLMENT_KEY,
    queryFn: () => getReportEnrollment(),
    staleTime: AVAILABILITY_STALE_MS
  });
}

export function useSetReportEnrollmentMutation() {
  const queryClient = useQueryClient();
  return useMutation<ReportEnrollment, Error, boolean>({
    mutationFn: (enabled: boolean) => setReportEnrollment(enabled),
    onSuccess: (data) => {
      queryClient.setQueryData<ReportEnrollment>(ENROLLMENT_KEY, data);
    }
  });
}
