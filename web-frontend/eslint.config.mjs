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
  files: ["src/**/*.{ts,tsx}"],
  ignores: ["src/**/*.test.{ts,tsx}", "src/test/**"],
  languageOptions: {
    parserOptions: { projectService: true, tsconfigRootDir: import.meta.dirname },
  },
  rules: {
    "@typescript-eslint/no-floating-promises": "error",
  },
}, {
  files: [
    "src/compat/scheduleSpec.ts",
    "src/hooks/{schedulingStorage,schedulingHistory,schedulingDataUpdate,schedulingReferenceUpdates}.ts",
    "src/app/ai-assistant/{aiClient,chatHistory,sessionEventRouter}.ts",
  ],
  rules: {
    "@typescript-eslint/no-unsafe-argument": "error",
    "@typescript-eslint/no-unsafe-assignment": "error",
    "@typescript-eslint/no-unsafe-call": "error",
    "@typescript-eslint/no-unsafe-member-access": "error",
    "@typescript-eslint/no-unsafe-return": "error",
  },
}, {
  ignores: ["node_modules/**", ".next/**", "out/**", "build/**", "coverage/**", "coverage-e2e/**", ".e2e-coverage/**", "test-results/**", "playwright-report/**", "next-env.d.ts"]
}];

export default eslintConfig;
