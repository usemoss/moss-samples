
/**
 * Lowest `modelArtifactContractVersion` that carries exact model artifact
 * identities through to the native session constructors.
 */
export const MIN_MODEL_ARTIFACT_CONTRACT_VERSION = 1;

/**
 * Guard a native session factory before handing it an exact model artifact
 * identity.
 *
 * The gate is a *minimum*, not an equality: a runtime advertising a higher
 * contract version is a newer core that still honours this one, and rejecting
 * it would make every SDK release a hard upper bound on the core it can run
 * against. Anything that cannot prove it implements the contract is refused
 * with the same curated upgrade error, so the failure stays closed:
 *
 *  - the property is missing, or is present but not callable (a malformed
 *    native module, which must not surface as a raw `TypeError`);
 *  - the reported version is not a number, is `NaN`/infinite, is fractional,
 *    or is outside the safe integer range, where equality and ordering stop
 *    being meaningful;
 *  - the reported version is below the minimum this SDK was written against.
 *
 * An exception thrown by a real callable is deliberately *not* caught: that is
 * the runtime reporting its own failure and the caller should see it verbatim.
 */
export function assertModelArtifactContractSupported(factory: {
  modelArtifactContractVersion?: () => number;
}): void {
  const reportContractVersion = factory.modelArtifactContractVersion;
  if (typeof reportContractVersion !== "function") {
    throw unsupportedCoreRuntime();
  }
  const version = reportContractVersion.call(factory);
  if (
    !Number.isSafeInteger(version) ||
    version < MIN_MODEL_ARTIFACT_CONTRACT_VERSION
  ) {
    throw unsupportedCoreRuntime();
  }
}

function unsupportedCoreRuntime(): Error {
  return new Error(
    "The installed @moss-js/moss-core runtime does not support exact model artifact identities. Upgrade moss-core before creating this session.",
  );
}
