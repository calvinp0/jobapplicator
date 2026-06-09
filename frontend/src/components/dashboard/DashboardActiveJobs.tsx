import { Link } from "react-router-dom";
import { buildActiveJobCard, type JobView } from "../../lib/dashboardJobs";
import { EmptyState } from "../ui";
import { ApplicationCard } from "./ApplicationCard";

interface DashboardActiveJobsProps {
  views: JobView[];
}

/**
 * The dashboard "Active jobs" section. Renders one {@link ApplicationCard} per
 * active job in a responsive grid, or a polished empty state when there is
 * nothing in flight.
 */
export function DashboardActiveJobs({ views }: DashboardActiveJobsProps) {
  const cards = views.map((view) => buildActiveJobCard(view));

  return (
    <section className="dashboard-section" aria-labelledby="dashboard-active-jobs">
      <h3 id="dashboard-active-jobs">Active jobs</h3>
      {cards.length === 0 ? (
        <EmptyState
          variant="inline"
          title="No active applications yet."
          description="Capture a job or add one manually to start tailoring."
          actions={
            <>
              <Link
                to="/jobs"
                className="ui-button ui-button-primary ui-button-sm"
              >
                Add job
              </Link>
              <Link
                to="/captures"
                className="ui-button ui-button-secondary ui-button-sm"
              >
                Open captures
              </Link>
            </>
          }
        />
      ) : (
        <ul className="application-card-grid">
          {cards.map((card) => (
            <ApplicationCard key={card.jobId} card={card} />
          ))}
        </ul>
      )}
    </section>
  );
}
