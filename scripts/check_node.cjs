// Validate the installed dependency tree, including native packages, without installing.
const path = require('node:path');
const root = path.resolve(__dirname, '../frontend');
const semver = require(path.join(root, 'node_modules/semver'));
for (const name of ['@angular/core', '@angular/cli', '@angular/build', 'vite', 'rollup', 'esbuild', 'jsdom', 'vitest']) {
  const pkg = require(path.join(root, 'node_modules', name, 'package.json'));
  if (pkg.engines?.node && !semver.satisfies(process.versions.node, pkg.engines.node)) {
    throw new Error(`${name}@${pkg.version} requires Node ${pkg.engines.node}; installed ${process.version}`);
  }
  console.log(`${name}@${pkg.version}: Node ${process.version} OK`);
}
// Real native loads: detect blocked/missing esbuild/Rollup before starting three services.
require(path.join(root, 'node_modules/rollup'));
require(path.join(root, 'node_modules/esbuild')).transformSync('const compatible = true;', {loader:'js'});
