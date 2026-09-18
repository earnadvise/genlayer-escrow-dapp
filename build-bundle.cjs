const esbuild = require('esbuild');

esbuild.buildSync({
  entryPoints: ['bundle-entry.js'],
  bundle: true,
  format: 'iife',
  globalName: 'GenLayerSDK',
  outfile: 'frontend/genlayer-bundle.js',
  platform: 'browser',
  define: {
    'process.env.NODE_ENV': '"production"',
    'global': 'window'
  }
});

console.log('genlayer-bundle.js bundled successfully!');
