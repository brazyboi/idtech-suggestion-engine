// Jest runs commonjs-transpiled code, where `import.meta` isn't valid syntax.
// Vite (the real build) never sees this file's plugin list — see vite.config.ts.
const stubImportMetaEnv = () => ({
  visitor: {
    MetaProperty(path) {
      path.replaceWithSourceString('({ env: { DEV: false } })');
    },
  },
});

module.exports = {
  presets: [
    ["@babel/preset-env", { targets: { node: "current" } }],
    ["@babel/preset-react", { runtime: "automatic" }],
    "@babel/preset-typescript",
  ],
  plugins: [stubImportMetaEnv],
};
