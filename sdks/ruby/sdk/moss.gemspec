# frozen_string_literal: true

require_relative "lib/moss/version"

Gem::Specification.new do |spec|
  spec.name        = "moss"
  spec.version     = Moss::VERSION
  spec.authors     = ["Moss"]
  spec.summary     = "Ruby SDK for Moss — real-time on-device semantic search."
  spec.description = <<~DESC
    The Moss Ruby SDK provides an ergonomic client over the Moss runtime for
    indexing, sub-10ms local semantic search, and metadata filtering, with a
    cloud query fallback. Local search is powered by the native libmoss runtime
    via the moss-core bindings; download libmoss from the usemoss/moss c-sdk
    releases and point MOSS_LIB_DIR at it to enable local operations.
  DESC
  spec.homepage = "https://github.com/usemoss/moss"
  spec.license  = "BSD-2-Clause"

  spec.required_ruby_version = ">= 3.0"

  spec.metadata = {
    "homepage_uri" => spec.homepage,
    "source_code_uri" => "https://github.com/usemoss/moss/tree/main/sdks/ruby/sdk",
    "documentation_uri" => "https://docs.moss.dev",
    "changelog_uri" => "https://github.com/usemoss/moss/blob/main/sdks/ruby/sdk/CHANGELOG.md",
    "rubygems_mfa_required" => "true"
  }

  spec.files = Dir[
    "lib/**/*.rb",
    "README.md",
    "LICENSE",
    "CHANGELOG.md"
  ]
  spec.require_paths = ["lib"]

  spec.add_dependency "moss-core", ">= 0.9", "< 1.0"

  spec.add_development_dependency "minitest", "~> 5.0"
  spec.add_development_dependency "rake", "~> 13.0"
  spec.add_development_dependency "rubocop", "~> 1.60"
end
