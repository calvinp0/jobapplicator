import { forwardRef } from "react";
import type {
  AnchorHTMLAttributes,
  ButtonHTMLAttributes,
  ReactNode,
} from "react";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
export type ButtonSize = "sm" | "md";

interface CommonProps {
  variant?: ButtonVariant;
  size?: ButtonSize;
  className?: string;
  children: ReactNode;
}

type NativeButtonProps = Omit<
  ButtonHTMLAttributes<HTMLButtonElement>,
  "className" | "children"
> &
  CommonProps;

function classesFor(variant: ButtonVariant, size: ButtonSize, extra?: string) {
  const out = ["ui-button", `ui-button-${variant}`];
  if (size === "sm") out.push("ui-button-sm");
  if (extra) out.push(extra);
  return out.join(" ");
}

/**
 * Polished button used across the redesigned shell. Four variants
 * (primary / secondary / ghost / danger) plus a compact `sm` size for
 * inline row actions. Use this in preference to raw `<button>` so the
 * cockpit keeps a single button hierarchy.
 */
export const Button = forwardRef<HTMLButtonElement, NativeButtonProps>(
  function Button(
    { variant = "primary", size = "md", className, children, type, ...rest },
    ref,
  ) {
    return (
      <button
        ref={ref}
        type={type ?? "button"}
        className={classesFor(variant, size, className)}
        {...rest}
      >
        {children}
      </button>
    );
  },
);

type NativeAnchorProps = Omit<
  AnchorHTMLAttributes<HTMLAnchorElement>,
  "className" | "children"
> &
  CommonProps;

/**
 * Anchor counterpart for places where the action is navigation (NavLink /
 * external link) but should look like a button. Use only when an anchor
 * is semantically correct — otherwise prefer `Button`.
 */
export function ButtonLink({
  variant = "primary",
  size = "md",
  className,
  children,
  ...rest
}: NativeAnchorProps) {
  return (
    <a className={classesFor(variant, size, className)} {...rest}>
      {children}
    </a>
  );
}
