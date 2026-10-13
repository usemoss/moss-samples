# frozen_string_literal: true

# Session sample: build an index in memory, query it locally, then push it to
# the cloud. Sessions require an enterprise plan.
#
# Run:
#   MOSS_LIB_DIR=/path/to/libmoss/lib \
#   MOSS_PROJECT_ID=... MOSS_PROJECT_KEY=... \
#   ruby sdks/ruby/sdk/samples/session_usage_sample.rb

$LOAD_PATH.unshift(File.expand_path("../lib", __dir__))
$LOAD_PATH.unshift(File.expand_path("../../bindings/lib", __dir__))

require "moss"

client = Moss::Client.new
session = client.session("scratch-session-sample")

begin
  session.add_documents([
                          Moss::DocumentInfo.new(id: "1", text: "Cats are small domesticated carnivores.",
                                                 metadata: { "kind" => "cat" }),
                          Moss::DocumentInfo.new(id: "2", text: "Dogs are loyal companion animals.",
                                                 metadata: { "kind" => "dog" })
                        ])
  puts "Session holds #{session.doc_count} documents."

  result = session.query("feline pet", top_k: 2)
  result.docs.each { |doc| puts "  #{doc.id}  score=#{format("%.3f", doc.score)}  #{doc.text}" }

  puts "Pushing session to the cloud..."
  push = session.push_index
  puts "Pushed: job=#{push.job_id} docs=#{push.doc_count}"
rescue Moss::Core::NativeError, Moss::Error => e
  raise unless e.message.match?(/enterprise|plan not allowed/i)

  puts "Sessions require an enterprise plan; skipping."
ensure
  session.close
  client.close
end
