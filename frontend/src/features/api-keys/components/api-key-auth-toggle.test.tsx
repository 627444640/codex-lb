import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ApiKeyAuthToggle } from "@/features/api-keys/components/api-key-auth-toggle";

describe("managed API key authentication", () => {
  it("blocks disabling required authentication", async () => {
    const onChange = vi.fn();
    render(<ApiKeyAuthToggle enabled requiredByDeployment onChange={onChange} />);
    await userEvent.click(screen.getByRole("switch"));
    expect(screen.getByRole("switch")).toBeDisabled();
    expect(onChange).not.toHaveBeenCalled();
    expect(screen.getByText(/requires API key authentication/)).toBeInTheDocument();
  });

  it("allows repairing disabled authentication", async () => {
    const onChange = vi.fn();
    render(<ApiKeyAuthToggle enabled={false} requiredByDeployment onChange={onChange} />);
    await userEvent.click(screen.getByRole("switch"));
    expect(onChange).toHaveBeenCalledWith(true);
  });
});
