import { goto } from '$app/navigation';
import * as api from './api';
import type { User } from './types';

/**
 * The signed-in user, as a rune-backed store.
 *
 * Only the profile lives here. Tokens are httpOnly cookies the browser cannot
 * read, so there is deliberately nothing token-shaped to keep in memory.
 */
class SessionStore {
  #user = $state<User | null>(null);
  #loading = $state(false);

  get user(): User | null {
    return this.#user;
  }

  get isAuthenticated(): boolean {
    return this.#user !== null;
  }

  get loading(): boolean {
    return this.#loading;
  }

  /** Seeded by the layout load so the first paint is not a flash of nothing. */
  hydrate(user: User | null): void {
    this.#user = user;
  }

  async refreshProfile(): Promise<User | null> {
    this.#loading = true;
    try {
      this.#user = await api.currentUser();
      return this.#user;
    } catch {
      this.#user = null;
      return null;
    } finally {
      this.#loading = false;
    }
  }

  async signOut(redirectTo = '/login'): Promise<void> {
    try {
      await api.logout();
    } finally {
      // Clear locally even if the call failed — the user asked to leave, and
      // the cookies are gone or unusable either way.
      this.#user = null;
      await goto(redirectTo, { invalidateAll: true });
    }
  }
}

export const session = new SessionStore();
