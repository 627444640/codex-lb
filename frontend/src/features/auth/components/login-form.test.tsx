import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { LoginForm } from "@/features/auth/components/login-form";
import { useAuthStore } from "@/features/auth/hooks/use-auth";
import { createDashboardAuthSession } from "@/test/mocks/factories";
import { server } from "@/test/mocks/server";

describe("LoginForm", () => {
  beforeEach(() => {
    useAuthStore.setState({
      loading: false,
      error: null,
      passwordRequired: true,
      guestAccessEnabled: false,
      guestPasswordRequired: false,
      loginGuest: vi.fn(),
    });
  });

  it("renders and submits password", async () => {
    const user = userEvent.setup();
    const clearError = vi.fn();
    const login = vi.fn().mockResolvedValue(undefined);

    useAuthStore.setState({
      clearError,
      login,
      loading: false,
      error: null,
    });

    render(<LoginForm />);

    await user.type(screen.getByLabelText("Password"), "secret-pass");
    await user.click(screen.getByRole("button", { name: "Sign In" }));

    expect(clearError).toHaveBeenCalledTimes(1);
    expect(login).toHaveBeenCalledWith("secret-pass");
  });

  it("shows error message when present", () => {
    useAuthStore.setState({
      error: "Invalid credentials",
      loading: false,
    });

    render(<LoginForm />);
    expect(screen.getByText("Invalid credentials")).toBeInTheDocument();
  });

  it("renders and submits guest password when guest access is enabled", async () => {
    const user = userEvent.setup();
    const clearError = vi.fn();
    const loginGuest = vi.fn().mockResolvedValue(undefined);

    useAuthStore.setState({
      clearError,
      loginGuest,
      passwordRequired: false,
      guestAccessEnabled: true,
      guestPasswordRequired: true,
      loading: false,
      error: null,
    });

    render(<LoginForm />);

    await user.type(screen.getByLabelText("Guest password"), "guest-pass");
    await user.click(screen.getByRole("button", { name: "View as Guest" }));

    expect(clearError).toHaveBeenCalledTimes(1);
    expect(loginGuest).toHaveBeenCalledWith("guest-pass");
  });

  it("submits passwordless guest access without a password", async () => {
    const user = userEvent.setup();
    const clearError = vi.fn();
    const loginGuest = vi.fn().mockResolvedValue(undefined);

    useAuthStore.setState({
      clearError,
      loginGuest,
      passwordRequired: false,
      guestAccessEnabled: true,
      guestPasswordRequired: false,
      loading: false,
      error: null,
    });

    render(<LoginForm />);

    await user.click(screen.getByRole("button", { name: "View as Guest" }));

    expect(clearError).toHaveBeenCalledTimes(1);
    expect(loginGuest).toHaveBeenCalledWith(undefined);
  });

  it("disables input and submit while loading", () => {
    useAuthStore.setState({
      loading: true,
      error: null,
    });

    render(<LoginForm />);
    expect(screen.getByLabelText("Password")).toBeDisabled();
    expect(screen.getByRole("button", { name: "Sign In" })).toBeDisabled();
  });

  it.each(["admin", "guest"] as const)("handles a rejected %s password and permits a successful retry", async (role) => {
    const user = userEvent.setup();
    const guest = role === "guest";
    useAuthStore.setState({
      ...useAuthStore.getInitialState(),
      passwordRequired: !guest,
      guestAccessEnabled: guest,
      guestPasswordRequired: guest,
      authenticated: false,
      permissions: [],
      canWrite: false,
    }, true);
    const submittedPasswords: string[] = [];
    server.use(http.post(`*/api/dashboard-auth/${guest ? "guest/login" : "password/login"}`, async ({ request }) => {
      const body = await request.json() as { password: string };
      submittedPasswords.push(body.password);
      if (body.password !== "correct-password") {
        return HttpResponse.json({ error: { code: "invalid_credentials", message: "Invalid credentials" } }, { status: 401 });
      }
      return HttpResponse.json(createDashboardAuthSession({
        authenticated: true,
        passwordRequired: !guest,
        guestAccessEnabled: guest,
        guestPasswordRequired: guest,
        role,
        permissions: guest ? ["read"] : ["read", "write"],
      }));
    }));
    const unhandled = vi.fn();
    window.addEventListener("unhandledrejection", unhandled);
    try {
      render(<LoginForm />);
      const input = screen.getByLabelText(guest ? "Guest password" : "Password");
      const submit = screen.getByRole("button", { name: guest ? "View as Guest" : "Sign In" });
      await user.type(input, "wrong-password");
      await user.click(submit);
      expect(await screen.findByText("Invalid credentials")).toBeVisible();
      expect(useAuthStore.getState().authenticated).toBe(false);
      expect(submit).toBeEnabled();
      await user.clear(input);
      await user.type(input, "correct-password");
      await user.click(submit);
      await waitFor(() => expect(useAuthStore.getState().authenticated).toBe(true));
      expect(screen.queryByText("Invalid credentials")).not.toBeInTheDocument();
      expect(useAuthStore.getState().role).toBe(role);
      expect(useAuthStore.getState().canWrite).toBe(!guest);
      expect(submittedPasswords).toEqual(["wrong-password", "correct-password"]);
      expect(unhandled).not.toHaveBeenCalled();
    } finally {
      window.removeEventListener("unhandledrejection", unhandled);
    }
  });
});
