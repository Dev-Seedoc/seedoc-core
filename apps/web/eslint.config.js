import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import globals from "globals";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["dist", "coverage", "test-results", "playwright-report", "src/lib/api/schema.d.ts"] },
  {
    extends: [js.configs.recommended, ...tseslint.configs.strictTypeChecked],
    files: ["**/*.{ts,tsx}"],
    languageOptions: {
      ecmaVersion: 2022,
      globals: globals.browser,
      parserOptions: { projectService: true, tsconfigRootDir: import.meta.dirname },
    },
    plugins: {
      "react-hooks": reactHooks,
      "react-refresh": reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      "react-refresh/only-export-components": ["warn", { allowConstantExport: true }],
    },
  },
  {
    // shadcn/ui files are generated and export helpers next to components.
    files: ["src/components/ui/**"],
    rules: { "react-refresh/only-export-components": "off" },
  },
  {
    // Playwright runs in Node, not in the browser; its fixtures call `use()`, which is not React's hook.
    files: ["e2e/**", "playwright.config.ts"],
    languageOptions: { globals: globals.node },
    rules: { "react-hooks/rules-of-hooks": "off", "react-refresh/only-export-components": "off" },
  },
);
