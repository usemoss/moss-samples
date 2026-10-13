# frozen_string_literal: true

# Metadata filtering sample: create a small catalog, load it locally, and run
# queries filtered with $eq, $and, and $in operators.
#
# Filters require a locally loaded index and use the engine's filter schema:
# each leaf is { "field" => name, "condition" => { "$op" => value } }.
#
# Run:
#   MOSS_LIB_DIR=/path/to/libmoss/lib \
#   MOSS_PROJECT_ID=... MOSS_PROJECT_KEY=... \
#   ruby sdks/ruby/sdk/samples/metadata_filtering_sample.rb

$LOAD_PATH.unshift(File.expand_path("../lib", __dir__))
$LOAD_PATH.unshift(File.expand_path("../../bindings/lib", __dir__))

require "moss"

client = Moss::Client.new
index_name = "catalog-filter-sample"

documents = [
  Moss::DocumentInfo.new(id: "p-1", text: "Trail running shoes with grippy soles.",
                         metadata: { "category" => "shoes", "city" => "portland", "price" => "80" }),
  Moss::DocumentInfo.new(id: "p-2", text: "Waterproof hiking boots.",
                         metadata: { "category" => "shoes", "city" => "denver", "price" => "140" }),
  Moss::DocumentInfo.new(id: "p-3", text: "Lightweight rain jacket.",
                         metadata: { "category" => "outerwear", "city" => "portland", "price" => "120" })
]

def show(label, result)
  puts label
  result.docs.each { |doc| puts "  #{doc.id}  score=#{format("%.3f", doc.score)}  #{doc.text}" }
end

eq_filter = { "field" => "category", "condition" => { "$eq" => "shoes" } }
and_filter = {
  "$and" => [
    { "field" => "category", "condition" => { "$eq" => "shoes" } },
    { "field" => "price", "condition" => { "$lt" => "100" } }
  ]
}
in_filter = { "field" => "city", "condition" => { "$in" => ["portland"] } }

begin
  client.create_index(index_name, documents)
  client.load_index(index_name)

  show("$eq category == shoes:", client.query(index_name, "footwear", top_k: 5, filter: eq_filter))
  show("$and shoes AND price < 100:", client.query(index_name, "footwear", top_k: 5, filter: and_filter))
  show("$in city in [portland]:", client.query(index_name, "gear", top_k: 5, filter: in_filter))
ensure
  begin
    client.unload_index(index_name)
  rescue StandardError
    # ignore
  end
  client.delete_index(index_name)
  client.close
end
