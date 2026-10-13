# frozen_string_literal: true

# Custom embeddings sample: index documents that already carry vectors and query
# by a raw embedding. When documents provide embeddings, the SDK infers the
# `custom` model automatically.
#
# Run:
#   MOSS_LIB_DIR=/path/to/libmoss/lib \
#   MOSS_PROJECT_ID=... MOSS_PROJECT_KEY=... \
#   ruby sdks/ruby/sdk/samples/custom_embeddings_sample.rb

$LOAD_PATH.unshift(File.expand_path("../lib", __dir__))
$LOAD_PATH.unshift(File.expand_path("../../bindings/lib", __dir__))

require "moss"

client = Moss::Client.new
index_name = "custom-embeddings-sample"

documents = [
  Moss::DocumentInfo.new(id: "doc-1", text: "First custom vector.", embedding: [1.0, 0.0, 0.0, 0.0]),
  Moss::DocumentInfo.new(id: "doc-2", text: "Second custom vector.", embedding: [0.0, 1.0, 0.0, 0.0]),
  Moss::DocumentInfo.new(id: "doc-3", text: "Third custom vector.", embedding: [0.0, 0.0, 1.0, 0.0])
]

begin
  puts "Creating custom-embedding index (model inferred as 'custom')..."
  client.create_index(index_name, documents)
  client.load_index(index_name)

  puts "Querying by embedding [1, 0, 0, 0]..."
  result = client.query(index_name, "", embedding: [1.0, 0.0, 0.0, 0.0], top_k: 3)
  result.docs.each { |doc| puts "  #{doc.id}  score=#{format("%.3f", doc.score)}" }
ensure
  begin
    client.unload_index(index_name)
  rescue StandardError
    # ignore
  end
  client.delete_index(index_name)
  client.close
end
