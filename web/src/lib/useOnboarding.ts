import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import { useAuth } from "./auth";

const LOCAL_KEY = "tp.onboarded";

/** Decides whether the guided first-run flow opens, and remembers that it's been seen.
 *
 *  With auth on, the flag lives on the user row (`onboarded_at`), so it follows them
 *  across devices and a colleague's dismissal doesn't hide it from you. With auth off
 *  (local/dev instances have no user at all) it falls back to localStorage — otherwise
 *  the flow would be impossible to reach there.
 *
 *  Dismiss and finish are the same thing on purpose: once you've seen it, we stop
 *  opening it by itself. `start()` reopens it from the sidebar. */
export function useOnboarding() {
  const { loading, authEnabled, user, refresh } = useAuth();
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (loading) return;
    const seen = authEnabled
      ? !user || !!user.onboarded_at // no user yet => login page is showing; not ours to open over
      : localStorage.getItem(LOCAL_KEY) === "1";
    if (!seen) setOpen(true);
  }, [loading, authEnabled, user]);

  const close = useCallback(async () => {
    setOpen(false);
    localStorage.setItem(LOCAL_KEY, "1");
    if (authEnabled && user) {
      await api.setOnboarded().catch(() => {});
      await refresh().catch(() => {});
    }
  }, [authEnabled, user, refresh]);

  const start = useCallback(() => setOpen(true), []);

  return { open, start, close };
}
