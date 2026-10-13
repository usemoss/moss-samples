const {
  createRunOncePlugin,
  withPodfileProperties,
} = require('@expo/config-plugins');

const pkg = require('./package.json');

/** Must stay in sync with `s.platforms` in ios/MossReactNative.podspec. */
const MIN_IOS_DEPLOYMENT_TARGET = '16.4';

/**
 * Compares dotted version strings numerically ("15.10" > "15.9").
 * @returns {number} negative if `a < b`, 0 if equal, positive if `a > b`
 */
const compareVersions = (a, b) => {
  const pa = String(a).split('.');
  const pb = String(b).split('.');
  for (let i = 0; i < Math.max(pa.length, pb.length); i += 1) {
    const na = Number.parseInt(pa[i], 10) || 0;
    const nb = Number.parseInt(pb[i], 10) || 0;
    if (na !== nb) {
      return na - nb;
    }
  }
  return 0;
};

/**
 * True when the existing target is unset, unparseable, or older than the
 * minimum Moss.xcframework supports.
 */
const needsBump = (current) => {
  if (current === undefined || current === null || String(current).trim() === '') {
    return true;
  }
  if (!/^\d+(\.\d+)*$/.test(String(current).trim())) {
    return true;
  }
  return compareVersions(current, MIN_IOS_DEPLOYMENT_TARGET) < 0;
};

/**
 * Expo config plugin for `@moss-dev/moss-react-native`.
 *
 * Raises the iOS deployment target to what Moss.xcframework requires and
 * documents that a development build / prebuild is required (Expo Go is not
 * supported because this module ships custom native code).
 *
 * An app that already pins a lower target (say `15.1`) is bumped rather than
 * left alone — CocoaPods rejects the pod otherwise.
 *
 * @param {import('@expo/config-plugins').ConfigPlugin} config
 */
const withMoss = (config) => {
  config = withPodfileProperties(config, (cfg) => {
    const current = cfg.modResults['ios.deploymentTarget'];
    if (needsBump(current)) {
      cfg.modResults['ios.deploymentTarget'] = MIN_IOS_DEPLOYMENT_TARGET;
    }
    return cfg;
  });
  return config;
};

module.exports = createRunOncePlugin(withMoss, pkg.name, pkg.version);
