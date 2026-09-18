import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
    "test-results/**",
    "playwright-report/**",
    // Ephemeral workflow worktrees (Demo Closure Sprint etc.) contain full
    // repo copies including dist/ builds that blow the eslint heap.
    ".claude/worktrees/**",
    // Archived bundles and immutable recording snapshots are not source.
    "defense/**/dist/**",
    "defense/**/deployed-dist/**",
    "defense/demo60/scripted/revisions/baseline/**",
  ]),
]);

export default eslintConfig;
