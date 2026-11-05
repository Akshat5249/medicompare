import { FlatCompat } from "@eslint/eslintrc";

const compat = new FlatCompat({ baseDirectory: import.meta.dirname });

export default [
  { ignores: [".next/**", "coverage/**", "playwright-report/**", "test-results/**", "public/**"] },
  ...compat.extends("next/core-web-vitals", "next/typescript"),
];
