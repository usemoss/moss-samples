# frozen_string_literal: true

# Comprehensive Moss Ruby SDK sample: create an index, load it locally, run a
# semantic query, read documents, and clean up.
#
# Run from the repo:
#   MOSS_LIB_DIR=/path/to/libmoss/lib \
#   MOSS_PROJECT_ID=... MOSS_PROJECT_KEY=... \
#   ruby sdks/ruby/sdk/samples/comprehensive_sample.rb

$LOAD_PATH.unshift(File.expand_path("../lib", __dir__))
$LOAD_PATH.unshift(File.expand_path("../../bindings/lib", __dir__))

require "moss"

client = Moss::Client.new
index_name = "support-docs-sample"

documents = [
  Moss::DocumentInfo.new(
    id: "doc-1",
    text: "Refunds are processed within five to seven business days.",
    metadata: { "topic" => "refunds" }
  ),
  Moss::DocumentInfo.new(
    id: "doc-2",
    text: "Orders can be tracked from the account dashboard.",
    metadata: { "topic" => "shipping" }
  ),
  Moss::DocumentInfo.new(
    id: "doc-3",
    text: "Contact support any time via live chat.",
    metadata: { "topic" => "support" }
  )
]

begin
  puts "Creating index '#{index_name}'..."
  result = client.create_index(index_name, documents, on_progress: lambda { |p|
    puts "  #{p.status} #{(p.progress * 100).round}%"
  })
  puts "Created: job=#{result.job_id} docs=#{result.doc_count}"

  info = client.get_index(index_name)
  puts "Index status: #{info.status} (model #{info.model.id})"

  puts "Loading index locally..."
  client.load_index(index_name)

  puts "Querying: 'how long do refunds take?'"
  search = client.query(index_name, "how long do refunds take?", top_k: 3)
  search.docs.each do |doc|
    puts "  #{doc.id}  score=#{format("%.3f", doc.score)}  #{doc.text}"
  end
  puts "  (#{search.time_taken_ms} ms)"

  puts "Stored documents:"
  client.get_documents(index_name).each { |doc| puts "  #{doc.id}: #{doc.metadata.inspect}" }
ensure
  puts "Cleaning up..."
  begin
    client.unload_index(index_name)
  rescue StandardError
    # ignore
  end
  client.delete_index(index_name)
  client.close
end
