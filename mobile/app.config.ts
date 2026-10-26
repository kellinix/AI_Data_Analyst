import type { ConfigContext, ExpoConfig } from 'expo/config';

export default ({ config }: ConfigContext): ExpoConfig => {
  const development = process.env.EAS_BUILD_PROFILE !== 'production';
  return {
    ...config,
    name: 'Zephyr', slug: 'zephyr-mobile', scheme: 'zephyr', version: '1.0.0',
    orientation: 'default', userInterfaceStyle: 'light',
    ios: {
      ...config.ios,
      supportsTablet: true,
      bundleIdentifier: process.env.ZEPHYR_IOS_BUNDLE_IDENTIFIER ?? 'com.zephyr.analytics',
      infoPlist: { ITSAppUsesNonExemptEncryption: false, ...(development ? { NSAppTransportSecurity: { NSAllowsLocalNetworking: true, NSAllowsArbitraryLoads: true } } : {}) },
    },
    android: {
      ...config.android,
      package: process.env.ZEPHYR_ANDROID_PACKAGE ?? 'com.zephyr.analytics',
      predictiveBackGestureEnabled: true,
      blockedPermissions: ['android.permission.RECORD_AUDIO', 'android.permission.READ_EXTERNAL_STORAGE', 'android.permission.WRITE_EXTERNAL_STORAGE'],
      adaptiveIcon: { foregroundImage: './assets/android-icon-foreground.png', monochromeImage: './assets/android-icon-monochrome.png', backgroundColor: '#F6F8FC' },
    },
    plugins: [
      'expo-router', 'expo-secure-store', 'expo-dev-client', 'expo-font',
      ['expo-build-properties', { android: { usesCleartextTraffic: development } }],
    ],
    web: { ...config.web, bundler: 'metro', output: 'single', name: 'Zephyr' },
  };
};
