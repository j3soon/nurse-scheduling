import nextCoreWebVitals from "eslint-config-next/core-web-vitals";
import nextTypescript from "eslint-config-next/typescript";

const eslintConfig = [...nextCoreWebVitals, ...nextTypescript, {
  rules: {
    // Require files to end with a newline
    "eol-last": ["error", "always"],
    // Disallow trailing whitespace at the end of lines
    "no-trailing-spaces": "error",
    // Allow unused parameters that start with underscore
    "@typescript-eslint/no-unused-vars": ["error", { "argsIgnorePattern": "^_" }],
  },
}, {
  ignores: ["node_modules/**", ".next/**", "out/**", "build/**", "coverage/**", "coverage-e2e/**", ".e2e-coverage/**", "test-results/**", "playwright-report/**", "next-env.d.ts"]
}];

export default eslintConfig;
