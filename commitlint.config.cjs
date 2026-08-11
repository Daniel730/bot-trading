/** @type {import('@commitlint/types').UserConfig} */
module.exports = {
  extends: ["@commitlint/config-conventional"],
  rules: {
    // Allow repo PR titles / Portuguese summaries without blocking agents.
    "subject-case": [0],
    "header-max-length": [2, "always", 120],
  },
};
