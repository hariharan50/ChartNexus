import type { HandleClientError } from '@sveltejs/kit';

export const handleClientError: HandleClientError = ({ error, status, message }) => {
  console.error('[client]', status, error);
  const detail = status < 500 ? message : 'An unexpected error occurred.';
  return { message: detail, code: 'client_error', detail };
};
