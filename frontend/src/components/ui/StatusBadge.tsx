import type { ReactNode } from "react";

export type StatusBadgeVariant =
  | "default"
  | "draft"
  | "pending"
  | "running"
  | "completed"
  | "approved"
  | "submitted"
  | "rejected"
  | "interview"
  | "offer"
  | "failed";

interface StatusBadgeProps {
  variant?: StatusBadgeVariant;
  children: ReactNode;
  "data-testid"?: string;
  className?: string;
}

export function StatusBadge({
  variant = "default",
  children,
  className,
  ...rest
}: StatusBadgeProps) {
  const classes = ["status-badge"];
  if (variant !== "default") {
    classes.push(`status-badge-${variant}`);
  }
  if (className) classes.push(className);
  return (
    <span className={classes.join(" ")} data-testid={rest["data-testid"]}>
      {children}
    </span>
  );
}
