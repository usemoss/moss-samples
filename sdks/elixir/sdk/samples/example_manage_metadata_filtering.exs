# Example: Metadata filtering with Moss.Client
#
# Counterpart to samples/metadata_filtering.py of the Python SDK
#
# Demonstrates metadata-filtered queries on a locally loaded cloud index.
# Filter operators shown: $eq, $and, $in, $near
#
# Usage:
#   mix run samples/example_manage_metadata_filtering.exs

# Load credentials from elixir/.env if present.
env_path = Path.join(__DIR__, "../.env")
if File.exists?(env_path) do
  env_path |> File.read!() |> String.split("\n", trim: true)
  |> Enum.reject(&(String.starts_with?(&1, "#") or &1 == ""))
  |> Enum.each(fn line ->
    case String.split(line, "=", parts: 2) do
      [k, v] -> System.put_env(String.trim(k), String.trim(v))
      _ -> :ok
    end
  end)
end

defmodule Sample.ManageMetadataFiltering do
  def run do
    project_id  = System.get_env("MOSS_PROJECT_ID")
    project_key = System.get_env("MOSS_PROJECT_KEY")

    unless project_id && project_key do
      IO.puts("Please set MOSS_PROJECT_ID and MOSS_PROJECT_KEY")
      exit(:normal)
    end

    IO.puts("Moss Metadata Filtering Sample (Elixir)")

    {:ok, client} = Moss.Client.new(project_id, project_key)

    documents = [
      %Moss.DocumentInfo{id: "doc1", text: "Running shoes with breathable mesh for daily training.",
        metadata: %{"category" => "shoes", "brand" => "swiftfit",   "price" => "79",  "city" => "new-york", "location" => "40.7580,-73.9855"}},
      %Moss.DocumentInfo{id: "doc2", text: "Trail running shoes built for rocky mountain terrain.",
        metadata: %{"category" => "shoes", "brand" => "peakstride", "price" => "149", "city" => "seattle",  "location" => "47.6062,-122.3321"}},
      %Moss.DocumentInfo{id: "doc3", text: "Lightweight city backpack with laptop compartment.",
        metadata: %{"category" => "bags",  "brand" => "urbanpack",  "price" => "95",  "city" => "new-york", "location" => "40.7505,-73.9934"}},
    ]

    ts = DateTime.utc_now() |> Calendar.strftime("%Y%m%d-%H%M%S")
    index_name = "metadata-filter-sample-#{ts}"

    try do
      IO.puts("\n1. Creating index...")
      {:ok, _} = Moss.Client.create_index(client, index_name, documents, "moss-minilm")

      IO.puts("2. Loading index locally (required for filtering)...")
      {:ok, _} = Moss.Client.load_index(client, index_name)

      IO.puts("\n3. $eq filter: category == shoes")
      {:ok, results} = Moss.Client.query(client, index_name, "running gear",
        top_k: 5, alpha: 0.5, filter: %{"field" => "category", "condition" => %{"$eq" => "shoes"}})
      print_results(results)

      IO.puts("\n4. $and filter: shoes and price < 100")
      {:ok, results} = Moss.Client.query(client, index_name, "running shoes",
        top_k: 5, alpha: 0.6,
        filter: %{"$and" => [
          %{"field" => "category", "condition" => %{"$eq" => "shoes"}},
          %{"field" => "price",    "condition" => %{"$lt" => "100"}}
        ]})
      print_results(results)

      IO.puts("\n5. $in filter: city in [new-york]")
      {:ok, results} = Moss.Client.query(client, index_name, "city essentials",
        top_k: 5, filter: %{"field" => "city", "condition" => %{"$in" => ["new-york"]}})
      print_results(results)

      IO.puts("\n6. $near filter: within 5km of Times Square")
      {:ok, results} = Moss.Client.query(client, index_name, "city products",
        top_k: 5, filter: %{"field" => "location", "condition" => %{"$near" => "40.7580,-73.9855,5000"}})
      print_results(results)

      IO.puts("\nMetadata filtering sample completed.")
    after
      IO.puts("\n7. Cleaning up index...")
      Moss.Client.delete_index(client, index_name)
    end
  end

  defp print_results(%{docs: docs}) do
    Enum.each(docs, fn doc ->
      IO.puts("- #{doc.id} | score=#{Float.round(doc.score, 3)} | metadata=#{inspect(doc.metadata)}")
    end)
  end
end

Sample.ManageMetadataFiltering.run()
