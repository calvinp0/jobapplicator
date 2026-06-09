import type { ActivityResponse } from "../../api";
import { ActivityItem } from "./ActivityItem";

// Render order for the grouped sections. The backend tags each item with a
// ``group`` so the popover stays a dumb renderer — it never inspects run or
// capture types to decide where a row belongs.
const GROUPS: { key: string; label: string }[] = [
  { key: "running", label: "Running" },
  { key: "attention", label: "Needs attention" },
  { key: "recent", label: "Recent" },
];

interface ActivityPopoverProps {
  activity: ActivityResponse | null;
  /** Closes the popover once the user clicks an item. */
  onNavigate: () => void;
}

export function ActivityPopover({ activity, onNavigate }: ActivityPopoverProps) {
  const items = activity?.items ?? [];

  return (
    <div className="activity-popover" role="dialog" aria-label="Activity center">
      <div className="activity-popover-header">
        <p className="activity-popover-title">Activity</p>
      </div>
      {items.length === 0 ? (
        <p className="activity-popover-empty">
          Nothing running — you&rsquo;re all caught up.
        </p>
      ) : (
        GROUPS.map((group) => {
          const groupItems = items.filter((item) => item.group === group.key);
          if (groupItems.length === 0) return null;
          return (
            <div className="activity-group" key={group.key}>
              <p className="activity-group-label">{group.label}</p>
              <ul className="activity-list">
                {groupItems.map((item) => (
                  <ActivityItem
                    key={item.id}
                    item={item}
                    onNavigate={onNavigate}
                  />
                ))}
              </ul>
            </div>
          );
        })
      )}
    </div>
  );
}
