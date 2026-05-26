import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import {
  EmptyState,
  PageHeader,
  SectionCard,
  SettingsGroup,
  StatusBadge,
} from "../components/ui";

describe("StatusBadge", () => {
  it("renders the default variant with just the base class", () => {
    render(<StatusBadge>Idle</StatusBadge>);
    const node = screen.getByText("Idle");
    expect(node).toHaveClass("status-badge");
    // No variant suffix should be added for the default variant.
    expect(node.className.split(/\s+/)).not.toContain("status-badge-default");
  });

  it("applies the variant class for a known variant", () => {
    render(<StatusBadge variant="rejected">Rejected</StatusBadge>);
    expect(screen.getByText("Rejected")).toHaveClass(
      "status-badge",
      "status-badge-rejected",
    );
  });

  it("forwards data-testid", () => {
    render(
      <StatusBadge variant="approved" data-testid="badge-x">
        Approved
      </StatusBadge>,
    );
    expect(screen.getByTestId("badge-x")).toHaveTextContent("Approved");
  });
});

describe("PageHeader", () => {
  it("renders title at h2 level with description and actions", () => {
    render(
      <PageHeader
        title="Demo"
        description="lorem"
        actions={<button>do thing</button>}
      />,
    );
    expect(screen.getByRole("heading", { level: 2 })).toHaveTextContent("Demo");
    expect(screen.getByText("lorem")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /do thing/i })).toBeInTheDocument();
  });
});

describe("SectionCard", () => {
  it("renders the title heading, description, and body content", () => {
    render(
      <SectionCard title="Sect" description="more">
        <p>body</p>
      </SectionCard>,
    );
    expect(
      screen.getByRole("heading", { level: 3, name: "Sect" }),
    ).toBeInTheDocument();
    expect(screen.getByText("more")).toBeInTheDocument();
    expect(screen.getByText("body")).toBeInTheDocument();
  });
});

describe("EmptyState", () => {
  it("renders title and description as a status region", () => {
    render(<EmptyState title="Nothing" description="here" />);
    const region = screen.getByRole("status");
    expect(region).toHaveTextContent("Nothing");
    expect(region).toHaveTextContent("here");
  });
});

describe("SettingsGroup", () => {
  it("renders a labelled section with its label and children", () => {
    render(
      <SettingsGroup label="Group" description="ctx">
        <p>contents</p>
      </SettingsGroup>,
    );
    const section = screen.getByRole("region", { name: "Group" });
    expect(section).toHaveTextContent("Group");
    expect(section).toHaveTextContent("ctx");
    expect(section).toHaveTextContent("contents");
  });
});
