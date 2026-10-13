package dev.moss.reactnative

import expo.modules.kotlin.exception.CodedException
import expo.modules.kotlin.modules.Module
import expo.modules.kotlin.modules.ModuleDefinition
import expo.modules.kotlin.sharedobjects.SharedObject
import expo.modules.kotlin.AppContext

/**
 * Android native builds of Moss are tracked in
 * https://github.com/usemoss/moss/issues/411. Until a published Android
 * artifact exists, constructing a client fails with a clear error so apps
 * can feature-detect.
 */
class MossModule : Module() {
  override fun definition() = ModuleDefinition {
    Name("Moss")

    Constant("sdkVersion") { "android-unavailable" }

    AsyncFunction("setModelCacheDir") { _: String ->
      throw AndroidUnavailableException()
    }

    Class("MossClient", MossClientSharedObject::class) {
      Constructor { _: String, _: String ->
        throw AndroidUnavailableException()
      }

      Function("close") { _: MossClientSharedObject -> }
    }
  }
}

class MossClientSharedObject(appContext: AppContext) : SharedObject(appContext)

class AndroidUnavailableException : CodedException(
  "Moss Android native builds are not published yet. Track progress in https://github.com/usemoss/moss/issues/411"
)
