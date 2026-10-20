# Example: Complete Moss Client cloud CRUD workflow
#
# Counterpart to samples/example_usage.py of the Python SDK
#
# Demonstrates:
#   1.  Create an index with documents
#   2.  Get index information
#   3.  List all indexes
#   4.  Add more documents
#   5.  Get all documents
#   6.  Get specific documents by ID
#   7.  Add documents with upsert
#   8.  Delete documents
#   9.  Verify count after deletion
#   10. Delete the index (cleanup)
#
# Usage:
#   mix run samples/example_manage_usage.exs

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

defmodule Sample.ManageUsage do
  def run do
    project_id  = System.get_env("MOSS_PROJECT_ID")
    project_key = System.get_env("MOSS_PROJECT_KEY")

    unless project_id && project_key do
      IO.puts("Please set MOSS_PROJECT_ID and MOSS_PROJECT_KEY")
      exit(:normal)
    end

    IO.puts("Moss Client Example")

    {:ok, client} = Moss.Client.new(project_id, project_key)

    documents = [
      %Moss.DocumentInfo{id: "doc1", text: "Machine learning is a subset of artificial intelligence that enables computers to learn from experience.",
        metadata: %{"category" => "ai", "topic" => "machine_learning", "difficulty" => "intermediate"}},
      %Moss.DocumentInfo{id: "doc2", text: "Deep learning uses neural networks with multiple layers to model complex patterns in data.",
        metadata: %{"category" => "ai", "topic" => "deep_learning", "difficulty" => "advanced"}},
      %Moss.DocumentInfo{id: "doc3", text: "Natural language processing enables computers to interpret and manipulate human language.",
        metadata: %{"category" => "ai", "topic" => "nlp", "difficulty" => "intermediate"}},
      %Moss.DocumentInfo{id: "doc4", text: "Computer vision enables machines to interpret and understand visual information.",
        metadata: %{"category" => "ai", "topic" => "computer_vision", "difficulty" => "intermediate"}},
      %Moss.DocumentInfo{id: "doc5", text: "Reinforcement learning is where an agent learns to make decisions by performing actions and receiving rewards.",
        metadata: %{"category" => "ai", "topic" => "reinforcement_learning", "difficulty" => "advanced"}},
    ]

    ts = DateTime.utc_now() |> Calendar.strftime("%Y%m%d-%H%M%S")
    index_name = "example-cloud-index-#{ts}"

    try do
      IO.puts("\n1. Creating index with documents...")
      {:ok, created} = Moss.Client.create_index(client, index_name, documents, "moss-minilm")
      IO.puts("   job_id: #{created.job_id}  doc_count: #{created.doc_count}")

      IO.puts("\n2. Getting index information...")
      {:ok, info} = Moss.Client.get_index(client, index_name)
      IO.puts("   name:      #{info.name}")
      IO.puts("   doc_count: #{info.doc_count}")
      IO.puts("   model:     #{info.model.id}")
      IO.puts("   status:    #{info.status}")

      IO.puts("\n3. Listing all indexes...")
      {:ok, indexes} = Moss.Client.list_indexes(client)
      IO.puts("   #{length(indexes)} index(es) found:")
      Enum.each(indexes, fn idx ->
        IO.puts("   - #{idx.name}: #{idx.doc_count} docs, status: #{idx.status}")
      end)

      IO.puts("\n4. Adding more documents...")
      new_docs = [
        %Moss.DocumentInfo{id: "doc6", text: "Data science combines statistics and programming to extract insights from data.",
          metadata: %{"category" => "data_science", "topic" => "analytics"}},
        %Moss.DocumentInfo{id: "doc7", text: "Cloud computing provides on-demand access to computing resources over the internet.",
          metadata: %{"category" => "infrastructure", "topic" => "cloud"}},
      ]
      {:ok, add_result} = Moss.Client.add_docs(client, index_name, new_docs, upsert: true)
      IO.puts("   doc_count: #{add_result.doc_count}")

      IO.puts("\n5. Getting all documents...")
      {:ok, all_docs} = Moss.Client.get_docs(client, index_name)
      IO.puts("   Total documents: #{length(all_docs)}")

      IO.puts("\n6. Getting specific documents...")
      {:ok, specific} = Moss.Client.get_docs(client, index_name, doc_ids: ["doc1", "doc2", "doc6"])
      IO.puts("   Fetched #{length(specific)} specific docs:")
      Enum.each(specific, fn doc ->
        preview = String.slice(doc.text, 0, 50)
        IO.puts("   - #{doc.id}: #{preview}...")
        if doc.metadata, do: IO.puts("     metadata: #{inspect(doc.metadata)}")
      end)

      IO.puts("\n7. Deleting some documents...")
      {:ok, del_result} = Moss.Client.delete_docs(client, index_name, ["doc6", "doc7"])
      IO.puts("   deleted: #{del_result.doc_count}")

      IO.puts("\n8. Verifying count after deletion...")
      {:ok, remaining} = Moss.Client.get_docs(client, index_name)
      IO.puts("   Remaining documents: #{length(remaining)}")

    after
      IO.puts("\n9. Cleaning up — deleting test index...")
      case Moss.Client.delete_index(client, index_name) do
        {:ok, true}  -> IO.puts("    Index deleted.")
        {:ok, false} -> IO.puts("    Index not found (already deleted).")
        {:error, e}  -> IO.puts("    Cleanup error: #{e}")
      end
    end

    IO.puts("\nAll operations completed.")
  end
end

Sample.ManageUsage.run()
