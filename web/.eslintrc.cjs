module.exports = {
  root: true,
  env: { browser: true, es2022: true, node: true },
  parser: "@typescript-eslint/parser",
  parserOptions: { ecmaVersion: "latest", sourceType: "module" },
  settings: { react: { version: "detect" } },
  extends: [
    "eslint:recommended",
    "plugin:@typescript-eslint/recommended",
    "plugin:eslint-comments/recommended",
    "plugin:react/recommended",
    "plugin:react-hooks/recommended",
    "prettier"
  ],
  plugins: [
    "@typescript-eslint",
    "eslint-comments",
    "react",
    "react-hooks",
    "prettier",
    "import"
  ],
  rules: {
    "react/prop-types": "off",
    "react/react-in-jsx-scope": "off",
    "react/no-unescaped-entities": "off",
    "@typescript-eslint/no-unused-vars": [
      "error",
      { argsIgnorePattern: "^_", varsIgnorePattern: "^_" }
    ],
    "no-constant-condition": "off",
    "spaced-comment": ["error", "always", { markers: ["/"] }],
    "no-warning-comments": [
      "warn",
      { terms: ["todo", "fixme", "xxx"], location: "start" }
    ],
    "eslint-comments/no-unlimited-disable": "error",
    "eslint-comments/no-unused-disable": "error",
    "eslint-comments/require-description": "error",
    "import/newline-after-import": ["error", { count: 1 }],
    "prettier/prettier": [
      "warn",
      {
        endOfLine: "auto"
      }
    ],
    "no-console": ["warn", { allow: ["warn", "error"] }]
  }
};
