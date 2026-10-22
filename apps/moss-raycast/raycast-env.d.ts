/// <reference types="@raycast/api">

/* 🚧 🚧 🚧
 * This file is auto-generated from the extension's manifest.
 * Do not modify manually. Instead, update the `package.json` file.
 * 🚧 🚧 🚧 */

/* eslint-disable @typescript-eslint/ban-types */

type ExtensionPreferences = {
  /** Project ID - Your Moss project ID */
  "projectId": string,
  /** Project Key - Your Moss project key */
  "projectKey": string,
  /** Index Name - Name of the Moss index to query */
  "indexName": string
}

/** Preferences accessible in all the extension's commands */
declare type Preferences = ExtensionPreferences

declare namespace Preferences {
  /** Preferences accessible in the `search-index` command */
  export type SearchIndex = ExtensionPreferences & {}
}

declare namespace Arguments {
  /** Arguments passed to the `search-index` command */
  export type SearchIndex = {}
}

