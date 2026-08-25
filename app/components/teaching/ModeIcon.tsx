import type { TeachingMode } from "./contracts";

export function ModeIcon({ mode }: { mode: TeachingMode }) {
  if (mode === "learn_concepts") {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <circle cx="12" cy="12" r="3.2" />
        <path d="M3.5 12c2.1-4.9 5-7.3 8.5-7.3s6.4 2.4 8.5 7.3c-2.1 4.9-5 7.3-8.5 7.3S5.6 16.9 3.5 12Z" />
      </svg>
    );
  }
  if (mode === "review_derivations") {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M5 5.5h5M5 12h3M5 18.5h5M15 4l4 4-4 4M19 8h-7M12 16h7" />
        <path d="m16 13 3 3-3 3" />
      </svg>
    );
  }
  if (mode === "run_experiments") {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M8 3h8M10 3v6l-5 8.2A2.5 2.5 0 0 0 7.1 21h9.8a2.5 2.5 0 0 0 2.1-3.8L14 9V3" />
        <path d="M7.3 16h9.4" />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M4 5.5h6l2 2h8v11H4Z" />
      <path d="M8 12h8M8 15.5h5" />
    </svg>
  );
}

