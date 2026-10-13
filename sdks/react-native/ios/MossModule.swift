import ExpoModulesCore
import MossC

public class MossModule: Module {
  public func definition() -> ModuleDefinition {
    Name("Moss")

    Constant("sdkVersion") {
      String(cString: moss_sdk_version())
    }

    // Emitted when an authenticator-backed client needs a bearer token. The JS
    // side answers with resolveAuthRequest / rejectAuthRequest.
    Events("onMossAuthRequest")

    AsyncFunction("setModelCacheDir") { (path: String) in
      try MossClientSharedObject.setModelCacheDir(path)
    }

    AsyncFunction("resolveAuthRequest") { (requestId: Int, token: String) in
      try MossClientSharedObject.resolveAuthRequest(
        requestId: try MossClientSharedObject.authRequestId(requestId),
        token: token
      )
    }

    AsyncFunction("rejectAuthRequest") { (requestId: Int, message: String?) in
      MossClientSharedObject.rejectAuthRequest(
        requestId: try MossClientSharedObject.authRequestId(requestId),
        message: message
      )
    }

    Class("MossClient", MossClientSharedObject.self) {
      Constructor { [weak self] (
        projectId: String,
        projectKey: String?,
        useAuthenticator: Bool,
        baseUrl: String?,
        clientId: Int
      ) -> MossClientSharedObject in
        guard useAuthenticator else {
          guard let projectKey, !projectKey.isEmpty else {
            throw MossClientSharedObject.argumentError("projectKey is required")
          }
          return try MossClientSharedObject(projectId: projectId, projectKey: projectKey)
        }
        // Called from an arbitrary native thread; just hands the request to JS.
        return try MossClientSharedObject(projectId: projectId, baseUrl: baseUrl) { requestId in
          self?.sendEvent(
            "onMossAuthRequest",
            ["clientId": clientId, "requestId": Int(requestId)]
          )
        }
      }

      AsyncFunction("createIndex") { (client: MossClientSharedObject, name: String, docsJson: String, modelId: String?) -> [String: Any] in
        try client.createIndex(name: name, docsJson: docsJson, modelId: modelId)
      }

      AsyncFunction("loadIndex") { (client: MossClientSharedObject, name: String, options: [String: Any]) in
        try client.loadIndex(name: name, options: options)
      }

      AsyncFunction("unloadIndex") { (client: MossClientSharedObject, name: String) in
        try client.unloadIndex(name: name)
      }

      AsyncFunction("query") { (client: MossClientSharedObject, name: String, query: String, options: [String: Any]) -> [String: Any] in
        try client.query(name: name, query: query, options: options)
      }

      AsyncFunction("listIndexes") { (client: MossClientSharedObject) -> [[String: Any]] in
        try client.listIndexes()
      }

      AsyncFunction("getIndex") { (client: MossClientSharedObject, name: String) -> [String: Any] in
        try client.getIndex(name: name)
      }

      AsyncFunction("deleteIndex") { (client: MossClientSharedObject, name: String) -> Bool in
        try client.deleteIndex(name: name)
      }

      AsyncFunction("addDocs") { (client: MossClientSharedObject, name: String, docsJson: String, upsert: Bool) -> [String: Any] in
        try client.addDocs(name: name, docsJson: docsJson, upsert: upsert)
      }

      Function("close") { (client: MossClientSharedObject) in
        client.close()
      }
    }
  }
}
