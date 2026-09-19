import js from "@eslint/js";
import tseslint from "typescript-eslint";
export default tseslint.config(
  {
    ignores: [
      ".next/**",
      "coverage/**",
      "next-env.d.ts",
      "lib/api-types.generated.ts",
    ],
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
);
