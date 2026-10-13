# frozen_string_literal: true

require_relative "moss/version"
require_relative "moss/errors"
require_relative "moss/models"
require_relative "moss/cloud_query"
require_relative "moss/session"
require_relative "moss/client"

# Moss is a real-time semantic search runtime for AI agents. This gem is the
# Ruby SDK: an ergonomic client over the native `libmoss` runtime for indexing,
# local sub-10ms search, and metadata filtering, with a cloud query fallback.
#
#   require "moss"
#
#   client = Moss::Client.new(project_id: "...", project_key: "...")
#   client.create_index("support-docs", [
#     Moss::DocumentInfo.new(id: "1", text: "Refunds take 5-7 business days.",
#                            metadata: { "topic" => "refunds" })
#   ])
#   client.load_index("support-docs")
#   result = client.query("support-docs", "how long do refunds take?", top_k: 3)
#   result.docs.each { |doc| puts "#{doc.id} #{doc.score}" }
module Moss
  # Returns the libmoss C SDK version reported by the loaded native runtime, or
  # nil when libmoss is unavailable.
  def self.libmoss_version
    Moss::Core.libmoss_sdk_version
  end

  # True when the native libmoss runtime can be loaded (local index + query).
  # When false, the SDK still supports cloud-backed queries.
  def self.native_runtime_available?
    Moss::Core.available?
  end
end
