// Flat config (ESLint 9). This exists because of a specific, expensive bug:
// on 2026-08-27 the Morning Brief tab called `tvUrl(...)`, a helper that was
// never defined. Vite does not resolve free identifiers at build time, so
// `npm run build` was clean, the bundle shipped, and the ReferenceError
// unmounted the ENTIRE dashboard at render. `no-undef` -- from js.recommended
// below, and the whole reason browser globals are declared -- catches exactly
// that class before it can be deployed again.
import js from "@eslint/js";
import globals from "globals";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";

export default [
  { ignores: ["dist/**", "node_modules/**"] },
  {
    files: ["**/*.{js,jsx}"],
    languageOptions: {
      ecmaVersion: "latest",
      sourceType: "module",
      // Without this, every `fetch`/`console`/`setInterval` reads as undefined
      // and no-undef becomes noise nobody looks at.
      globals: globals.browser,
      parserOptions: {
        ecmaFeatures: { jsx: true },
      },
    },
    plugins: {
      "react-hooks": reactHooks,
      "react-refresh": reactRefresh,
    },
    rules: {
      ...js.configs.recommended.rules,
      ...reactHooks.configs.recommended.rules,
      "react-refresh/only-export-components": [
        "warn", { allowConstantExport: true },
      ],
      // JSX use counts as a use -- otherwise every component reads as unused.
      "no-unused-vars": ["error", { varsIgnorePattern: "^[A-Z_]" }],
    },
  },
];
