import "@testing-library/jest-dom/vitest";
import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";

// Auto-unmount React trees + clear globals between tests so leftover DOM
// from a previous test never leaks into the next assertion.
afterEach(() => {
  cleanup();
});
