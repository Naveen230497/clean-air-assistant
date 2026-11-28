module.exports = [
  {
    ignores: ["app/static/leaflet.js"],
  },
  {
    files: ["app/static/*.js"],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "script",
    },
    rules: {
      "complexity": ["error", 10],
      "max-depth": ["error", 3],
      "max-lines-per-function": ["error", {max: 40, IIFEs: false, skipBlankLines: true, skipComments: true}],
      "no-console": "error",
    },
  },
];
