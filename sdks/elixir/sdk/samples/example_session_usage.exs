# Example: Live Call Session Indexing with moss Elixir SDK
#
# Counterpart to samples/example_session_usage.py of the Python SDK
#
# Demonstrates the full session workflow:
#   1. Open a session — auto-loads from cloud if the index exists, starts fresh if not
#   2. Index call transcript turns locally during the call
#   3. Query the local session index (no cloud round trip)
#   4. Add more turns mid-call
#   5. Push the session index to cloud at call end
#
# Usage:
#   mix run samples/example_session_usage.exs

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

defmodule Sample.SessionUsage do
  def ms(start), do: "#{System.monotonic_time(:millisecond) - start}ms"

  def run do
    project_id  = System.get_env("MOSS_PROJECT_ID")
    project_key = System.get_env("MOSS_PROJECT_KEY")

    unless project_id && project_key do
      IO.puts("Please set MOSS_PROJECT_ID and MOSS_PROJECT_KEY")
      IO.puts("Copy samples/.env.template to samples/.env and source it")
      exit(:normal)
    end

    {:ok, client} = Moss.Client.new(project_id, project_key)

    # -- Simulated call data --------------------------------------------------
    ts     = DateTime.utc_now() |> Calendar.strftime("%Y%m%d-%H%M%S")
    call_id = "call-#{ts}"

    transcript = [
      {"turn-1", "Customer called about an incorrect charge on their March invoice."},
      {"turn-2", "The customer was billed twice for the same subscription renewal."},
      {"turn-3", "Customer requested a refund for the duplicate charge of $49.99."},
      {"turn-4", "Agent confirmed the refund would be processed in 3-5 business days."},
      {"turn-5", "Customer also asked about upgrading to the Business plan."},
      {"turn-6", "Agent explained Business plan includes 1TB storage at $79.99/month."},
      {"turn-7", "Customer decided to upgrade immediately after hearing the benefits."},
    ]

    IO.puts("\n--- Starting session: #{call_id} ---\n")

    # -- Step 1: Open session -------------------------------------------------
    t = System.monotonic_time(:millisecond)
    {:ok, session} = Moss.Client.session(client, call_id, model_id: "moss-minilm")
    doc_count = Moss.Session.doc_count(session)
    IO.puts("Session ready: #{inspect(call_id)}  (#{doc_count} existing docs)  [#{ms(t)}]")

    # -- Step 2: Index transcript turns ---------------------------------------
    IO.puts("\nIndexing call transcript locally...")
    docs = Enum.map(transcript, fn {id, text} -> %Moss.DocumentInfo{id: id, text: text} end)

    t = System.monotonic_time(:millisecond)
    {:ok, {added, updated}} = Moss.Session.add_docs(session, docs)
    IO.puts("  #{added} turns added, #{updated} updated  (total: #{Moss.Session.doc_count(session)})  [#{ms(t)}]")

    # -- Step 3: Query the local session index --------------------------------
    IO.puts("\nQuerying session index (local, no cloud)...")
    queries = [
      "billing issue and invoice dispute",
      "refund processing timeline",
      "plan upgrade storage",
    ]

    Enum.each(queries, fn query_text ->
      t = System.monotonic_time(:millisecond)
      {:ok, results} = Moss.Session.query(session, query_text, top_k: 2)
      IO.puts("\n  Query: #{inspect(query_text)}  [#{ms(t)}]")
      Enum.each(results.docs, fn doc ->
        IO.puts("    [#{doc.id}] score=#{Float.round(doc.score, 3)}  #{String.slice(doc.text, 0, 60)}...")
      end)
    end)

    # -- Step 4: Add more turns mid-call --------------------------------------
    IO.puts("\nAdding follow-up turns...")
    follow_ups = [
      %Moss.DocumentInfo{id: "turn-8", text: "Agent initiated the plan upgrade and sent confirmation email."},
      %Moss.DocumentInfo{id: "turn-9", text: "Customer confirmed they received the email and were satisfied."},
    ]
    t = System.monotonic_time(:millisecond)
    {:ok, _} = Moss.Session.add_docs(session, follow_ups)
    IO.puts("  Session now has #{Moss.Session.doc_count(session)} documents  [#{ms(t)}]")

    t = System.monotonic_time(:millisecond)
    {:ok, result} = Moss.Session.query(session, "call resolution and next steps", top_k: 3)
    IO.puts("\n  Final context query results  [#{ms(t)}]:")
    Enum.each(result.docs, fn doc ->
      IO.puts("    [#{doc.id}] score=#{Float.round(doc.score, 3)}  #{String.slice(doc.text, 0, 60)}...")
    end)

    # -- Step 5: Push session index to cloud ----------------------------------
    IO.puts("\nPushing session index to cloud as #{inspect(call_id)}...")
    t = System.monotonic_time(:millisecond)
    {:ok, push_result} = Moss.Session.push_index(session)
    IO.puts("  job_id:    #{push_result.job_id}  [#{ms(t)}]")
    IO.puts("  index:     #{push_result.index_name}")
    IO.puts("  doc_count: #{push_result.doc_count}")
    IO.puts("  status:    #{push_result.status}")

    IO.puts("\nDone! Next run with the same call_id will auto-load this index.")
  end
end

Sample.SessionUsage.run()
