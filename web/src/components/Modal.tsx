import clsx from "clsx";
import { useCallback, useEffect, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

// Centered, animated modal with enter + exit animations. Backdrop click & Esc close it.
// Children may be a render function receiving `close` so their own buttons animate out too.
export function Modal({
  onClose,
  className,
  overlayClassName,
  children,
}: {
  onClose: () => void;
  className?: string;
  /** extra classes on the scrim — set a higher z when opening a modal from inside one */
  overlayClassName?: string;
  children: ReactNode | ((close: () => void) => ReactNode);
}) {
  const [closing, setClosing] = useState(false);

  const close = useCallback(() => {
    setClosing(true);
    setTimeout(onClose, 150); // let the exit animation finish before unmount
  }, [onClose]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [close]);

  // Portal to <body>: a transformed/filtered ancestor (layout animations) would
  // otherwise make `fixed inset-0` relative to that ancestor, leaving the top bar
  // uncovered. Rendering at body root guarantees the scrim covers the whole viewport.
  return createPortal(
    <div
      className={clsx(
        "fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-[#23242d80] p-6 backdrop-blur-[2px] sm:items-center",
        closing ? "tp-overlay-out" : "tp-overlay",
        overlayClassName,
      )}
      onClick={close}
    >
      <div
        className={clsx("w-full", className ?? "max-w-lg", closing ? "tp-pop-out" : "tp-pop")}
        onClick={(e) => e.stopPropagation()}
      >
        {typeof children === "function" ? children(close) : children}
      </div>
    </div>,
    document.body,
  );
}
