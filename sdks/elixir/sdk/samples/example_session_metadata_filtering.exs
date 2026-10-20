# Example: Metadata Filtering in a Session Index
#
# Counterpart to samples/session_metadata_filtering.py of the Python SDK
#
# Demonstrates querying a local session index with metadata filters.
# All filter operations run in-memory — no cloud round trips during the session.
#
# Filter operators shown: $eq, $ne, $gt, $in, $and, $or, $near
#
# Usage:
#   mix run samples/example_session_metadata_filtering.exs

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

defmodule Sample.SessionMetadataFiltering do
  def ms(start), do: "#{System.monotonic_time(:millisecond) - start}ms"

  @transcript [
    %Moss.DocumentInfo{
      id: "t1", text: "Customer opened the call about an incorrect charge on their March invoice.",
      metadata: %{"speaker" => "agent", "topic" => "billing", "priority" => "3", "location" => "40.7580,-73.9855"}
    },
    %Moss.DocumentInfo{
      id: "t2", text: "The account was billed twice for the same subscription renewal on March 5th.",
      metadata: %{"speaker" => "agent", "topic" => "billing", "priority" => "5", "location" => "40.7580,-73.9855"}
    },
    %Moss.DocumentInfo{
      id: "t3", text: "I need a full refund for the duplicate charge of $49.99 immediately.",
      metadata: %{"speaker" => "customer", "topic" => "refund", "priority" => "5", "location" => "40.6892,-74.0445"}
    },
    %Moss.DocumentInfo{
      id: "t4", text: "The refund will be processed within 3 to 5 business days to your original payment method.",
      metadata: %{"speaker" => "agent", "topic" => "refund", "priority" => "4", "location" => "40.7580,-73.9855"}
    },
    %Moss.DocumentInfo{
      id: "t5", text: "Can you also tell me what is included in the Business plan upgrade?",
      metadata: %{"speaker" => "customer", "topic" => "upgrade", "priority" => "2", "location" => "40.6892,-74.0445"}
    },
    %Moss.DocumentInfo{
      id: "t6", text: "The Business plan includes 1TB storage, priority support, and team collaboration at $79.99 per month.",
      metadata: %{"speaker" => "agent", "topic" => "upgrade", "priority" => "2", "location" => "40.7580,-73.9855"}
    },
    %Moss.DocumentInfo{
      id: "t7", text: "That sounds good, I would like to upgrade my plan right now.",
      metadata: %{"speaker" => "customer", "topic" => "upgrade", "priority" => "3", "location" => "40.6892,-74.0445"}
    },
    %Moss.DocumentInfo{
      id: "t8", text: "I have processed the plan upgrade and sent a confirmation email to your address.",
      metadata: %{"speaker" => "agent", "topic" => "upgrade", "priority" => "3", "location" => "40.7580,-73.9855"}
    },
  ]

  def run do
    project_id  = System.get_env("MOSS_PROJECT_ID")
    project_key = System.get_env("MOSS_PROJECT_KEY")

    unless project_id && project_key do
      IO.puts("Please set MOSS_PROJECT_ID and MOSS_PROJECT_KEY")
      exit(:normal)
    end

    {:ok, client} = Moss.Client.new(project_id, project_key)
    ts = DateTime.utc_now() |> Calendar.strftime("%Y%m%d-%H%M%S")
    call_id = "filter-sample-#{ts}"

    IO.puts("\n--- Session: #{call_id} ---\n")

    t = System.monotonic_time(:millisecond)
    {:ok, session} = Moss.Client.session(client, call_id, model_id: "moss-minilm")
    {:ok, _} = Moss.Session.add_docs(session, @transcript)
    IO.puts("Session ready: #{Moss.Session.doc_count(session)} turns indexed  [#{ms(t)}]\n")

    run_filter(session, "1. $eq — customer turns only",
      "what did the customer say",
      %{"field" => "speaker", "condition" => %{"$eq" => "customer"}},
      fn doc -> "speaker=#{doc.metadata["speaker"]}" end)

    run_filter(session, "2. $ne — exclude agent turns",
      "what was discussed",
      %{"field" => "speaker", "condition" => %{"$ne" => "agent"}},
      fn doc -> "speaker=#{doc.metadata["speaker"]}" end)

    run_filter(session, "3. $gt — priority > 3",
      "urgent issues",
      %{"field" => "priority", "condition" => %{"$gt" => "3"}},
      fn doc -> "priority=#{doc.metadata["priority"]}" end)

    run_filter(session, "4. $in — topic in [billing, refund]",
      "payment and charges",
      %{"field" => "topic", "condition" => %{"$in" => ["billing", "refund"]}},
      fn doc -> "topic=#{doc.metadata["topic"]}" end)

    run_filter(session, "5. $and — agent + billing",
      "billing explanation",
      %{"$and" => [
        %{"field" => "speaker", "condition" => %{"$eq" => "agent"}},
        %{"field" => "topic",   "condition" => %{"$eq" => "billing"}}
      ]},
      fn doc -> "speaker=#{doc.metadata["speaker"]} topic=#{doc.metadata["topic"]}" end)

    run_filter(session, "6. $or — refund or upgrade",
      "account changes",
      %{"$or" => [
        %{"field" => "topic", "condition" => %{"$eq" => "refund"}},
        %{"field" => "topic", "condition" => %{"$eq" => "upgrade"}}
      ]},
      fn doc -> "topic=#{doc.metadata["topic"]}" end)

    run_filter(session, "7. $near — within 1km of Times Square",
      "agent response",
      %{"field" => "location", "condition" => %{"$near" => "40.7580,-73.9855,1000"}},
      fn doc -> "speaker=#{doc.metadata["speaker"]}" end)

    IO.puts("\nPushing session index to cloud as #{inspect(call_id)}...")
    t = System.monotonic_time(:millisecond)
    {:ok, push_result} = Moss.Session.push_index(session)
    IO.puts("  job_id:    #{push_result.job_id}  [#{ms(t)}]")
    IO.puts("  index:     #{push_result.index_name}")
    IO.puts("  doc_count: #{push_result.doc_count}")
    IO.puts("\nDone.")
  end

  defp run_filter(session, label, query_text, filter, meta_fn) do
    IO.puts(label)
    t = System.monotonic_time(:millisecond)
    {:ok, results} = Moss.Session.query(session, query_text, top_k: 5, filter: filter)
    IO.puts("   [#{ms(t)}]  #{length(results.docs)} result(s)")
    Enum.each(results.docs, fn doc ->
      IO.puts("   [#{doc.id}] score=#{Float.round(doc.score, 3)}  #{meta_fn.(doc)}  #{String.slice(doc.text, 0, 60)}...")
    end)
    IO.puts("")
  end
end

Sample.SessionMetadataFiltering.run()
