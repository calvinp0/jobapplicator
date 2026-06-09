import { Link } from "react-router-dom";
import type { ActivityItem as ActivityItemModel } from "../../api";

/**
 * Coarse "time since" label for an activity row. Kept deliberately fuzzy
 * ("3m ago" / "2h ago") — the activity center is a glanceable status
 * surface, not a precise timeline. Returns null when there is no usable
 * timestamp so the caller can omit the meta line entirely.
 */
function elapsedLabel(startedAt?: string | null): string | null {
  if (!startedAt) return null;
  const started = new Date(startedAt).getTime();
  if (Number.isNaN(started)) return null;
  const diffMs = Date.now() - started;
  if (diffMs < 0) return null;
  const mins = Math.floor(diffMs / 60_000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

interface ActivityItemProps {
  item: ActivityItemModel;
  /** Called after the user clicks through, so the popover can close. */
  onNavigate: () => void;
}

export function ActivityItem({ item, onNavigate }: ActivityItemProps) {
  const elapsed = elapsedLabel(item.started_at);
  return (
    <li className="activity-item">
      <Link to={item.href} className="activity-item-link" onClick={onNavigate}>
        <span
          className={`activity-item-dot activity-item-dot-${item.status}`}
          aria-hidden="true"
        />
        <span className="activity-item-body">
          <span className="activity-item-title">{item.title}</span>
          {item.subtitle ? (
            <span className="activity-item-subtitle">{item.subtitle}</span>
          ) : null}
          {item.detail ? (
            <span className="activity-item-detail">{item.detail}</span>
          ) : null}
          {elapsed ? (
            <span className="activity-item-meta">{elapsed}</span>
          ) : null}
        </span>
        <span className="activity-item-open" aria-hidden="true">
          Open
        </span>
      </Link>
    </li>
  );
}
