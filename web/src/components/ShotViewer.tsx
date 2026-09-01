import { ChevronLeft, ChevronRight } from "lucide-react";
import { useCallback, useEffect } from "react";
import { useTranslation } from "react-i18next";

import { Modal } from "./Modal";

export type Shot = { i: number; action?: string; screenshot: string | null };

/** Full-size viewer for a run's step screenshots. The thumbnails are ~120px wide and the
 *  live frame is cropped to 16/10 — neither is readable when the question is "what did the
 *  agent actually see in that form". Click one, then ← / → through the rest; Modal owns
 *  Esc and the backdrop click. */
export function ShotViewer({
  shots,
  index,
  onIndex,
  onClose,
}: {
  shots: Shot[];
  index: number;
  onIndex: (i: number) => void;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const total = shots.length;

  const go = useCallback(
    (delta: number) => {
      if (total > 1) onIndex((index + delta + total) % total);
    },
    [index, total, onIndex],
  );

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "ArrowLeft") go(-1);
      else if (e.key === "ArrowRight") go(1);
      else if (e.key === "Escape") {
        // Capture phase + stopPropagation: the replay modal this viewer opens from also
        // listens for Escape on window, so one press would otherwise dismiss both and
        // drop you back on the run list. Costs the 150ms exit animation, which is fine.
        e.stopPropagation();
        onClose();
      }
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [go, onClose]);

  const shot = shots[index];
  const src = shot?.screenshot;
  if (!src) return null; // bound to a local: narrowing on shot.screenshot is lost inside the render callback

  return (
    // z above the replay modal it can be opened from — both portal to <body>.
    <Modal onClose={onClose} overlayClassName="z-[60]" className="max-w-[94vw]">
      {(close) => (
        <div className="flex flex-col gap-2">
          <div className="flex flex-wrap items-center justify-between gap-3 text-sm text-white">
            <div className="flex items-center gap-2">
              <span className="font-medium">{t("Step {{n}}", { n: shot.i })}</span>
              {shot.action && (
                <span className="rounded bg-white/15 px-1.5 py-0.5 font-mono text-[11px]">{shot.action}</span>
              )}
            </div>
            <div className="flex items-center gap-3">
              {total > 1 && (
                <span className="tabular-nums text-white/70">
                  {index + 1} / {total}
                </span>
              )}
              <a
                href={src}
                target="_blank"
                rel="noreferrer"
                className="underline underline-offset-2 hover:text-white/80"
              >
                {t("open original")}
              </a>
              <button onClick={close} className="hover:text-white/80">
                {t("Close")}
              </button>
            </div>
          </div>

          <div className="relative">
            <img
              src={src}
              alt={`step ${shot.i}`}
              className="max-h-[82vh] w-full rounded-lg bg-white object-contain"
            />
            {total > 1 && (
              <>
                <NavButton side="left" label={t("previous step")} onClick={() => go(-1)} />
                <NavButton side="right" label={t("next step")} onClick={() => go(1)} />
              </>
            )}
          </div>
        </div>
      )}
    </Modal>
  );
}

function NavButton({ side, label, onClick }: { side: "left" | "right"; label: string; onClick: () => void }) {
  const Icon = side === "left" ? ChevronLeft : ChevronRight;
  return (
    <button
      aria-label={label}
      title={label}
      onClick={onClick}
      className={
        "absolute top-1/2 grid h-10 w-10 -translate-y-1/2 place-items-center rounded-full bg-black/45 text-white backdrop-blur-sm transition-colors hover:bg-black/70 " +
        (side === "left" ? "left-2" : "right-2")
      }
    >
      <Icon size={20} />
    </button>
  );
}
