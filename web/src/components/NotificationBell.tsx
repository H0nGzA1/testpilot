import clsx from "clsx";
import { Bell } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { api, relTime, type AppNotification } from "../lib/api";

export function NotificationBell() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [count, setCount] = useState(0);
  const [items, setItems] = useState<AppNotification[]>([]);
  const ref = useRef<HTMLDivElement>(null);

  const refreshCount = () =>
    api.unreadCount().then((r) => setCount(r.count)).catch(() => {});

  useEffect(() => {
    refreshCount();
    const id = setInterval(refreshCount, 30000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    if (!open) return;
    api.listNotifications().then(setItems).catch(() => {});
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  const openItem = async (n: AppNotification) => {
    if (!n.read) {
      await api.readNotification(n.id).catch(() => {});
      refreshCount();
    }
    setOpen(false);
    if (n.link) navigate(n.link);
  };

  const readAll = async () => {
    await api.readAllNotifications().catch(() => {});
    setItems((xs) => xs.map((x) => ({ ...x, read: true })));
    setCount(0);
  };

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        aria-label="notifications"
        className="relative flex h-8 w-8 items-center justify-center rounded-lg hover:bg-[var(--panel2)]"
      >
        <Bell className="h-4 w-4 text-ink-600" />
        {count > 0 && (
          <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-[1rem] items-center justify-center rounded-full bg-[var(--bad-fg)] px-1 text-[10px] font-semibold text-white">
            {count > 99 ? "99+" : count}
          </span>
        )}
      </button>
      {open && (
        <div className="absolute right-0 top-10 z-50 w-96 overflow-hidden rounded-xl border border-[var(--line)] bg-[var(--panel)] shadow-xl">
          <div className="flex items-center justify-between border-b border-[var(--line)] px-3 py-2">
            <span className="text-sm font-medium text-ink-900">{t("Notifications")}</span>
            <button className="text-xs text-brand-700 hover:underline" onClick={readAll}>
              {t("Mark all read")}
            </button>
          </div>
          <div className="max-h-[26rem] overflow-y-auto">
            {items.length === 0 && (
              <div className="px-3 py-8 text-center text-sm text-ink-400">{t("No notifications.")}</div>
            )}
            {items.map((n) => (
              <button
                key={n.id}
                onClick={() => openItem(n)}
                className={clsx(
                  "block w-full border-b border-[var(--line)] px-3 py-2.5 text-left last:border-0 hover:bg-brand-50/50",
                  !n.read && "bg-brand-50/30",
                )}
              >
                <div className="flex items-start gap-2">
                  {!n.read && <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-brand-500" />}
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-sm font-medium text-ink-900">{n.title}</div>
                    {n.body && <div className="mt-0.5 line-clamp-2 text-xs text-ink-500">{n.body}</div>}
                    <div className="mt-1 text-[11px] text-ink-400">{relTime(n.created_at)}</div>
                  </div>
                </div>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
