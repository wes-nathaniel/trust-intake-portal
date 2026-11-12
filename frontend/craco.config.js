// craco.config.js
const path = require("path");
require("dotenv").config();

// Check if we're in development/preview mode (not production build)
// Craco sets NODE_ENV=development for start, NODE_ENV=production for build
const isDevServer = process.env.NODE_ENV !== "production";

// Environment variable overrides
const config = {
  enableHealthCheck: process.env.ENABLE_HEALTH_CHECK === "true",
};

// Conditionally load health check modules only if enabled
let WebpackHealthPlugin;
let setupHealthEndpoints;
let healthPluginInstance;

if (config.enableHealthCheck) {
  WebpackHealthPlugin = require("./plugins/health-check/webpack-health-plugin");
  setupHealthEndpoints = require("./plugins/health-check/health-endpoints");
  healthPluginInstance = new WebpackHealthPlugin();
}

let webpackConfig = {
  eslint: {
    configure: {
      extends: ["plugin:react-hooks/recommended"],
      rules: {
        "react-hooks/rules-of-hooks": "error",
        "react-hooks/exhaustive-deps": "warn",
      },
    },
  },
  webpack: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
    configure: (webpackConfig) => {

      // Add ignored patterns to reduce watched directories
        webpackConfig.watchOptions = {
          ...webpackConfig.watchOptions,
          ignored: [
            '**/node_modules/**',
            '**/.git/**',
            '**/build/**',
            '**/dist/**',
            '**/coverage/**',
            '**/public/**',
        ],
      };

      // Add health check plugin to webpack if enabled
      if (config.enableHealthCheck && healthPluginInstance) {
        webpackConfig.plugins.push(healthPluginInstance);
      }
      return webpackConfig;
    },
  },
};

// Wrap with visual edits (automatically adds babel plugin, dev server, and overlay in dev mode)
if (isDevServer) {
  try {
    const { withVisualEdits } = require("@emergentbase/visual-edits/craco");
    webpackConfig = withVisualEdits(webpackConfig);
  } catch (err) {
    if (err.code === 'MODULE_NOT_FOUND' && err.message.includes('@emergentbase/visual-edits/craco')) {
      console.warn(
        "[visual-edits] @emergentbase/visual-edits not installed — visual editing disabled."
      );
    } else {
      throw err;
    }
  }
}

// ── OAuth well-known discovery endpoints ──────────────────────────────────────
// MUST run AFTER withVisualEdits so we wrap (not replace) whatever devServer it sets.
// RFC 8414 §3: for issuer https://trust.igchq.com/api/mcp/oauth the discovery URL is
// https://HOST/.well-known/oauth-authorization-server/api/mcp/oauth  (host ++ /.well-known/ ++ path).
// For the custom domain (trust.igchq.com) /.well-known/ routes to this dev-server (port 3000),
// not to the backend. We intercept here and serve the static files from public/.well-known/
// so the production URLs (trust.igchq.com) are always returned — not the preview env URL.
if (isDevServer) {
  const fs = require("fs");

  const readWellKnownFile = (relPath) => {
    try {
      return fs.readFileSync(path.join(__dirname, "public", ".well-known", relPath), "utf8");
    } catch (_) {
      return null;
    }
  };

  const oauthWellKnownMiddleware = (req, res, next) => {
    const url = req.url.split("?")[0];

    // Map well-known paths to their static file counterparts
    let filePath = null;
    if (
      url === "/.well-known/oauth-authorization-server/api/mcp/oauth" ||
      url === "/.well-known/oauth-authorization-server"
    ) {
      filePath = "oauth-authorization-server/api/mcp/oauth";
    } else if (url === "/.well-known/oauth-protected-resource") {
      filePath = "oauth-protected-resource";
    }

    if (!filePath) return next();

    if (req.method === "OPTIONS") {
      res.setHeader("Access-Control-Allow-Origin", "*");
      res.setHeader("Access-Control-Allow-Methods", "GET, OPTIONS");
      res.setHeader("Access-Control-Allow-Headers", "Content-Type, Authorization");
      res.writeHead(200);
      res.end();
      return;
    }

    const content = readWellKnownFile(filePath);
    if (!content) return next();

    res.setHeader("Content-Type", "application/json");
    res.setHeader("Access-Control-Allow-Origin", "*");
    res.setHeader("Cache-Control", "no-cache");
    res.writeHead(200);
    res.end(content);
  };

  const prevDevServerFn = webpackConfig.devServer;
  webpackConfig.devServer = (devServerConfig) => {
    // Run withVisualEdits' devServer transform first (if any)
    let config = typeof prevDevServerFn === "function" ? prevDevServerFn(devServerConfig) : devServerConfig;

    // Chain setupMiddlewares so our well-known handler runs at the very front
    const prevSetup = config.setupMiddlewares;
    config.setupMiddlewares = (middlewares, devServer) => {
      let result = typeof prevSetup === "function" ? prevSetup(middlewares, devServer) : middlewares;

      // Health check (keep existing behaviour)
      if (config.enableHealthCheck && setupHealthEndpoints && healthPluginInstance) {
        setupHealthEndpoints(devServer, healthPluginInstance);
      }

      // Our well-known middleware goes first so historyApiFallback never fires for these paths
      result.unshift({ name: "oauth-well-known", middleware: oauthWellKnownMiddleware });
      return result;
    };

    return config;
  };
}

module.exports = webpackConfig;
