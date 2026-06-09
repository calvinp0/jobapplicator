import { Link } from "react-router-dom";
import type { ActiveJobCard } from "../../lib/dashboardJobs";
import { ApplicationStatus } from "./ApplicationStatus";
import { ApplicationActionsMenu } from "./ApplicationActionsMenu";

interface ApplicationCardProps {
  card: ActiveJobCard;
}

/**
 * A single active-application card: title + metadata, one compact status, an
 * explicit "Next:" line, exactly one primary action button, and an overflow
 * menu for everything else. The muted activity line and optional failure
 * message sit at the bottom.
 */
export function ApplicationCard({ card }: ApplicationCardProps) {
  const meta = card.location
    ? `${card.company} · ${card.location}`
    : card.company;

  return (
    <li className="application-card">
      <div className="application-card-head">
        <Link to={`/jobs/${card.jobId}`} className="application-card-title">
          {card.title}
        </Link>
        <p className="application-card-meta">{meta}</p>
      </div>

      <div className="application-card-state">
        <ApplicationStatus variant={card.statusVariant}>
          {card.statusLabel}
        </ApplicationStatus>
        <p className="application-card-next">
          <span className="application-card-next-label">Next:</span>{" "}
          {card.nextLabel}
        </p>
      </div>

      {card.error ? (
        <p className="application-card-error" role="status">
          {card.error}
        </p>
      ) : null}

      <div className="application-card-actions">
        <Link
          to={card.primary.href}
          className="ui-button ui-button-primary ui-button-sm application-card-primary"
        >
          {card.primary.label}
        </Link>
        <ApplicationActionsMenu actions={card.secondary} label={card.title} />
      </div>

      {card.activity ? (
        <p className="application-card-activity">{card.activity}</p>
      ) : null}
    </li>
  );
}
