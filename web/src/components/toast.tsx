import clsx from "clsx";
import { CircleAlert, CircleCheck, Info, X } from "lucide-react";
import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from "react";

type Toast = { id: number; type: "success" | "error" | "info"; msg: string };
type Push = (type: Toast["type"], msg: string) => void;

const ToastCtx = createContext<Push>(() => {});

export function useToast() {
  return useContext(ToastCtx);
}

const ICON = { success: CircleCheck, error: CircleAlert, info: Info };
const STYLE = {
  error: "border-[var(--bad-fg)]/40 bg-[var(--bad-bg)] text-[var(--bad-fg)]",
  success: "border-[var(--ok-fg)]/40 bg-[var(--ok-bg)] text-[var(--ok-fg)]",
  info: "border-[var(--line)] bg-[var(--panel)] text-ink-800",
};

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const seq = useRef(0);

  const dismiss = useCallback((id: number) => setToasts((t) => t.filter((x) => x.id !== id)), []);
  const push = useCallback<Push>(
    (type, msg) => {
      const id = ++seq.current;
      setToasts((t) => [...t, { id, type, msg }]);
      // errors linger longer (harder to miss); others auto-dismiss sooner
      setTimeout(() => dismiss(id), type === "error" ? 8000 : 4500);
    },
    [dismiss],
  );

  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="fixed bottom-6 right-6 z-[100] flex w-[26rem] max-w-[calc(100vw-3rem)] flex-col gap-3">
        {toasts.map((t) => {
          const Icon = ICON[t.type];
          return (
            <div
              key={t.id}
              role="alert"
              className={clsx(
                "toast-in flex items-start gap-3 rounded-xl border border-l-4 px-4 py-3.5 text-sm font-medium shadow-xl ring-1 ring-black/5",
                STYLE[t.type],
              )}
            >
              <Icon className="mt-0.5 h-5 w-5 shrink-0" />
              <span className="flex-1 break-words leading-snug">{t.msg}</span>
              <button
                onClick={() => dismiss(t.id)}
                aria-label="close"
                className="-mr-1 -mt-0.5 shrink-0 rounded p-0.5 opacity-60 transition-opacity hover:opacity-100"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          );
        })}
      </div>
    </ToastCtx.Provider>
  );
}
