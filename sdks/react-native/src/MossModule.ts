import { requireNativeModule } from 'expo-modules-core';

/**
 * Low-level Expo native module handle.
 * Prefer the idiomatic {@link MossClient} wrapper exported from the package root.
 */
export default requireNativeModule('Moss');
