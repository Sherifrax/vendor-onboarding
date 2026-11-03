import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { expect, it } from "vitest";
import App from "./App";

it("shows the memory-only admin token entry point", () => {
  render(<QueryClientProvider client={new QueryClient()}><App /></QueryClientProvider>);
  expect(screen.getByRole("heading", { name: "Onboarding, visible." })).toBeInTheDocument();
  expect(screen.getByLabelText("Admin token")).toHaveAttribute("type", "password");
});
