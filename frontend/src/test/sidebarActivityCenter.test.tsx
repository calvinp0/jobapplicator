import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";

const { getActivityMock, listCapturesMock } = vi.hoisted(() => ({
  getActivityMock: vi.fn(),
  listCapturesMock: vi.fn(),
}));

vi.mock("../api", () => ({
  getActivity: getActivityMock,
  listCaptures: listCapturesMock,
}));

import { SidebarActivityCenter } from "../components/activity/SidebarActivityCenter";
import { Layout } from "../layout/Layout";
import type { ActivityResponse } from "../api";

function activity(
  summary: Partial<ActivityResponse["summary"]>,
  items: ActivityResponse["items"] = [],
): ActivityResponse {
  return {
    summary: {
      running_count: 0,
      attention_count: 0,
      pending_capture_count: 0,
      ...summary,
    },
    items,
  };
}

function LocationProbe() {
  const location = useLocation();
  return <div data-testid="location">{location.pathname}</div>;
}

afterEach(() => {
  vi.clearAllMocks();
});

describe("SidebarActivityCenter", () => {
  it("shows All clear when nothing is running or needs attention", async () => {
    getActivityMock.mockResolvedValue(activity({}));
    render(
      <MemoryRouter>
        <SidebarActivityCenter />
      </MemoryRouter>,
    );
    expect(await screen.findByText(/all clear/i)).toBeInTheDocument();
  });

  it("shows the running count when a run is active", async () => {
    getActivityMock.mockResolvedValue(activity({ running_count: 2 }));
    render(
      <MemoryRouter>
        <SidebarActivityCenter />
      </MemoryRouter>,
    );
    expect(await screen.findByText(/2 running/i)).toBeInTheDocument();
  });

  it("shows the attention count when items need review", async () => {
    getActivityMock.mockResolvedValue(activity({ attention_count: 3 }));
    render(
      <MemoryRouter>
        <SidebarActivityCenter />
      </MemoryRouter>,
    );
    expect(await screen.findByText(/3 need attention/i)).toBeInTheDocument();
  });

  it("opens a popover listing the running item and navigates on click", async () => {
    const user = userEvent.setup();
    getActivityMock.mockResolvedValue(
      activity({ running_count: 1 }, [
        {
          id: "run_1",
          type: "tailoring_run",
          status: "running",
          group: "running",
          title: "Tailoring resume",
          subtitle: "SciML Engineer — Example Aero Labs",
          started_at: null,
          href: "/runs/run_1",
        },
      ]),
    );
    render(
      <MemoryRouter initialEntries={["/"]}>
        <SidebarActivityCenter />
        <Routes>
          <Route path="*" element={<LocationProbe />} />
        </Routes>
      </MemoryRouter>,
    );

    await screen.findByText(/1 running/i);
    // The popover is closed until the user clicks the activity center.
    expect(
      screen.queryByRole("dialog", { name: /activity center/i }),
    ).toBeNull();

    await user.click(screen.getByRole("button", { name: /activity/i }));
    const dialog = await screen.findByRole("dialog", {
      name: /activity center/i,
    });
    expect(within(dialog).getByText("Tailoring resume")).toBeInTheDocument();
    expect(within(dialog).getByText(/SciML Engineer/)).toBeInTheDocument();

    await user.click(
      within(dialog).getByRole("link", { name: /tailoring resume/i }),
    );
    expect(screen.getByTestId("location")).toHaveTextContent("/runs/run_1");
  });

  it("surfaces a pending capture as an attention item linking to the capture", async () => {
    const user = userEvent.setup();
    getActivityMock.mockResolvedValue(
      activity({ attention_count: 1, pending_capture_count: 1 }, [
        {
          id: "cap_1",
          type: "pending_capture",
          status: "attention",
          group: "attention",
          title: "Capture needs review",
          subtitle: "Research Engineer",
          started_at: null,
          href: "/captures/cap_1",
        },
      ]),
    );
    render(
      <MemoryRouter>
        <SidebarActivityCenter />
      </MemoryRouter>,
    );

    await screen.findByText(/1 need attention/i);
    await user.click(screen.getByRole("button", { name: /activity/i }));
    const dialog = await screen.findByRole("dialog", {
      name: /activity center/i,
    });
    const link = within(dialog).getByRole("link", {
      name: /capture needs review/i,
    });
    expect(link).toHaveAttribute("href", "/captures/cap_1");
  });
});

describe("Layout captures nav demotion (task 117)", () => {
  function renderLayout() {
    getActivityMock.mockResolvedValue(activity({}));
    return render(
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<div>home</div>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );
  }

  it("hides the Capture inbox link when no captures are pending", async () => {
    listCapturesMock.mockResolvedValue([]);
    renderLayout();
    const primaryNav = screen.getByRole("navigation", { name: /primary/i });
    await waitFor(() =>
      expect(
        within(primaryNav).queryByRole("link", { name: /capture/i }),
      ).toBeNull(),
    );
  });

  it("shows the Capture inbox link when a capture is pending", async () => {
    listCapturesMock.mockResolvedValue([{ id: "c1", user_confirmed: false }]);
    renderLayout();
    const primaryNav = screen.getByRole("navigation", { name: /primary/i });
    const link = await within(primaryNav).findByRole("link", {
      name: /capture inbox/i,
    });
    expect(link).toHaveAttribute("href", "/captures");
  });
});
