# Example: Resume an existing cloud index, extend it in-session, push the update.
#
# Counterpart to samples/example_extend_index.py of the Python SDK
#
# session() automatically loads from cloud if the index exists, or starts fresh
# if it doesn't — the workflow is identical in both cases.
#
#   First run  — index doesn't exist yet, session starts empty
#   Second run — index exists in cloud, session auto-loads it, new docs are appended
#
# Usage:
#   MOSS_EXISTING_INDEX=my-session-index mix run samples/example_extend_index.exs

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

defmodule Sample.ExtendIndex do
  def ms(start), do: "#{System.monotonic_time(:millisecond) - start}ms"

  def run do
    project_id   = System.get_env("MOSS_PROJECT_ID")
    project_key  = System.get_env("MOSS_PROJECT_KEY")
    index_name   = System.get_env("MOSS_EXISTING_INDEX", "my-session-index")

    unless project_id && project_key do
      IO.puts("Please set MOSS_PROJECT_ID and MOSS_PROJECT_KEY")
      exit(:normal)
    end

    {:ok, client} = Moss.Client.new(project_id, project_key)

    IO.puts("Opening session for '#{index_name}'...")
    t = System.monotonic_time(:millisecond)
    {:ok, session} = Moss.Client.session(client, index_name, model_id: "moss-minilm")
    IO.puts("  Session ready — #{Moss.Session.doc_count(session)} existing docs loaded  [#{ms(t)}]")

    # Add new docs — appended to whatever was already loaded
    new_docs = [
      %Moss.DocumentInfo{id: "follow-up-1", text: "Customer called back to confirm refund was received."},
      %Moss.DocumentInfo{id: "follow-up-2", text: "Refund of $49.99 appeared on statement within 3 days."},
      %Moss.DocumentInfo{id: "follow-up-3", text: "Customer expressed satisfaction and closed the case."},
    ]

    IO.puts("\nAdding new docs...")
    t = System.monotonic_time(:millisecond)
    {:ok, {added, updated}} = Moss.Session.add_docs(session, new_docs)
    IO.puts("  #{added} added, #{updated} updated  (total: #{Moss.Session.doc_count(session)})  [#{ms(t)}]")

    # Query the combined index
    IO.puts("\nQuerying combined index...")
    t = System.monotonic_time(:millisecond)
    {:ok, results} = Moss.Session.query(session, "refund outcome and customer satisfaction", top_k: 3)
    IO.puts("  Query complete  [#{ms(t)}]")
    Enum.each(results.docs, fn doc ->
      IO.puts("    [#{doc.id}] score=#{Float.round(doc.score, 3)}  #{String.slice(doc.text, 0, 60)}...")
    end)

    # Push back to cloud — creates or overwrites
    IO.puts("\nPushing to cloud as '#{index_name}'...")
    t = System.monotonic_time(:millisecond)
    {:ok, push_result} = Moss.Session.push_index(session)
    IO.puts("  job_id:    #{push_result.job_id}  [#{ms(t)}]")
    IO.puts("  doc_count: #{push_result.doc_count}")
    IO.puts("  status:    #{push_result.status}")
  end
end

Sample.ExtendIndex.run()
