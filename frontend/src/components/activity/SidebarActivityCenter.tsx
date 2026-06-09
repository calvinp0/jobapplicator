import { useCallback, useEffect, useRef, useState } from "react";
import { getActivity } from "../../api";
import type { ActivityResponse, ActivitySummary } from "../../api";
import { ActivityPopover } from "./ActivityPopover";

// Poll cadence for the activity feed while the app is open. 15s matches the
// task brief: frequent enough to feel live for a running tailoring job,
// infrequent enough to stay quiet on a local backend.
const POLL_INTERVAL_MS = 15_000;

const EMPTY_SUMMARY: ActivitySummary = {
  running_count: 0,
  attention_count: 0,
  pending_capture_count: 0,
};

type Tone = "running" | "attention" | "idle";

// Collapsed-state priority: a running job is the most useful thing to
// surface, then anything needing attention, then the calm "all clear".
function statusTone(summary: ActivitySummary): Tone {
  if (summary.running_count > 0) return "running";
  if (summary.attention_count > 0) return "attention";
  return "idle";
}

function summaryLabel(summary: ActivitySummary): string {
  if (summary.running_count > 0) {
    return `${summary.running_count} running`;
  }
  if (summary.attention_count > 0) {
    return `${summary.attention_count} need attention`;
  }
  return "All clear";
}

export function SidebarActivityCenter() {
  const [activity, setActivity] = useState<ActivityResponse | null>(null);
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  // Activity is best-effort: a failed fetch keeps the last known state
  // (or the empty summary on first load) instead of surfacing an error in
  // the nav rail.
  const load = useCallback(() => {
    return getActivity()
      .then((data) => setActivity(data))
      .catch(() => {
        /* keep previous state — the activity center never blocks the app */
      });
  }, []);

  useEffect(() => {
    let active = true;
    load();
    const id = window.setInterval(() => {
      if (active) load();
    }, POLL_INTERVAL_MS);
    return () => {
      active = false;
      window.clearInterval(id);
    };
  }, [load]);

  // Dismiss on outside click and Escape, matching common popover semantics.
  useEffect(() => {
    if (!open) return;
    function onPointerDown(event: MouseEvent) {
      if (
        containerRef.current &&
        !containerRef.current.contains(event.target as Node)
      ) {
        setOpen(false);
      }
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  const summary = activity?.summary ?? EMPTY_SUMMARY;
  const tone = statusTone(summary);
  const label = summaryLabel(summary);

  function toggle() {
    setOpen((prev) => {
      const next = !prev;
      // Refetch on open so the popover reflects the latest state without
      // waiting for the next poll tick.
      if (next) load();
      return next;
    });
  }

  return (
    <div className="sidebar-activity" ref={containerRef}>
      <button
        type="button"
        className="sidebar-activity-trigger"
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={toggle}
      >
        <span
          className={`sidebar-activity-dot sidebar-activity-dot-${tone}`}
          aria-hidden="true"
        />
        <span className="sidebar-activity-text">
          <span className="sidebar-activity-label">Activity</span>
          <span className="sidebar-activity-detail">{label}</span>
        </span>
      </button>
      {open ? (
        <ActivityPopover activity={activity} onNavigate={() => setOpen(false)} />
      ) : null}
    </div>
  );
}
