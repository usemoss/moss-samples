# frozen_string_literal: true

require_relative "lib/moss/core/version"

Gem::Specification.new do |spec|
  spec.name        = "moss-core"
  spec.version     = Moss::Core::VERSION
  spec.authors     = ["Moss"]
  spec.summary     = "FFI bindings for the Moss semantic search engine (libmoss)."
  spec.description = <<~DESC
    Low-level Ruby bindings over the prebuilt libmoss C SDK. Provides
    ManageClient, IndexManager and Session primitives used by the high-level
    `moss` gem. Requires the libmoss shared library at runtime; download it from
    the usemoss/moss c-sdk releases and point MOSS_LIB_DIR (or MOSS_LIBRARY_PATH)
    at it.
  DESC
  spec.homepage = "https://github.com/usemoss/moss"
  spec.license  = "BSD-2-Clause"

  spec.required_ruby_version = ">= 3.0"

  spec.metadata = {
    "homepage_uri" => spec.homepage,
    "source_code_uri" => "https://github.com/usemoss/moss/tree/main/sdks/ruby/bindings",
    "documentation_uri" => "https://docs.moss.dev",
    "rubygems_mfa_required" => "true"
  }

  spec.files = Dir[
    "lib/**/*.rb",
    "README.md",
    "LICENSE"
  ]
  spec.require_paths = ["lib"]

  spec.add_dependency "ffi", "~> 1.15"

  spec.add_development_dependency "minitest", "~> 5.0"
  spec.add_development_dependency "rake", "~> 13.0"
end
