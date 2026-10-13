#!/usr/bin/env ruby
# frozen_string_literal: true

# Live end-to-end validation harness for the Moss Ruby SDK.
#
# This is the ONLY component that touches real credentials, and it does so at
# runtime only: it reads MOSS_PROJECT_ID / MOSS_PROJECT_KEY from the repo-root
# `.env` file into the process environment, never printing or persisting them.
# Every line written to stdout/stderr is passed through a scrubber that redacts
# the secret values as a defense-in-depth measure.
#
# It also auto-provisions the native libmoss C SDK into a gitignored vendor dir
# so the whole round-trip (create -> load -> query -> filter -> delete) runs
# locally.
#
# Usage:
#   ruby sdks/ruby/sdk/scripts/validate.rb
#
# Exit codes: 0 = all checks passed, 1 = a check failed, 2 = misconfiguration.

require "fileutils"

SCRIPT_DIR   = __dir__
REPO_ROOT    = File.expand_path("../../../..", SCRIPT_DIR)
SDK_LIB      = File.expand_path("../lib", SCRIPT_DIR)
BINDINGS_LIB = File.expand_path("../../bindings/lib", SCRIPT_DIR)
$LOAD_PATH.unshift(SDK_LIB, BINDINGS_LIB)

LIBMOSS_VERSION = "0.9.0"
VENDOR_DIR      = File.join(REPO_ROOT, "sdks", "ruby", ".libmoss")
ENV_FILE        = File.join(REPO_ROOT, ".env")
SECRET_KEYS     = %w[MOSS_PROJECT_ID MOSS_PROJECT_KEY].freeze

# --- credential loading (runtime only; values never printed) ---------------

def load_env_file(path)
  return unless File.exist?(path)

  File.foreach(path) do |raw|
    line = raw.strip
    next if line.empty? || line.start_with?("#")

    key, sep, value = line.partition("=")
    next if sep.empty?

    key = key.sub(/\Aexport\s+/, "").strip
    next if key.empty?

    value = value.strip
    if value.length >= 2 &&
       ((value.start_with?('"') && value.end_with?('"')) ||
        (value.start_with?("'") && value.end_with?("'")))
      value = value[1..-2]
    end
    ENV[key] ||= value
  end
end

# Redacts secret values from any text before it is displayed.
def build_scrubber
  secrets = SECRET_KEYS.map { |k| ENV.fetch(k, nil) }.compact.map(&:to_s).reject(&:empty?)
  lambda do |text|
    result = text.to_s
    secrets.each { |value| result = result.gsub(value, "[REDACTED]") }
    result
  end
end

# --- libmoss provisioning ---------------------------------------------------

def libmoss_target
  case RUBY_PLATFORM
  when /arm64-darwin/, /aarch64-darwin/ then "aarch64-apple-darwin"
  when /x86_64-darwin/                  then nil # no x86_64 macOS build in this release
  when /x86_64-linux/                   then "x86_64-unknown-linux-gnu"
  when /aarch64-linux/, /arm64-linux/   then "aarch64-unknown-linux-gnu"
  end
end

def libmoss_filename
  RUBY_PLATFORM.include?("darwin") ? "libmoss.dylib" : "libmoss.so"
end

def ensure_libmoss(log)
  return if ENV["MOSS_LIB_DIR"] || ENV["MOSS_LIBRARY_PATH"]

  target = libmoss_target
  unless target
    log.call("! No prebuilt libmoss for #{RUBY_PLATFORM}; set MOSS_LIB_DIR manually.")
    return
  end

  base    = "libmoss-v#{LIBMOSS_VERSION}-#{target}"
  lib_dir = File.join(VENDOR_DIR, base, "lib")
  lib_file = File.join(lib_dir, libmoss_filename)

  unless File.exist?(lib_file)
    FileUtils.mkdir_p(VENDOR_DIR)
    archive = "#{base}.tar.gz"
    url = "https://github.com/usemoss/moss/releases/download/c-sdk-v#{LIBMOSS_VERSION}/#{archive}"
    dest = File.join(VENDOR_DIR, archive)
    log.call("• Downloading libmoss (#{target})…")
    unless system("curl", "-sSL", "--fail", "-o", dest, url)
      log.call("! Failed to download libmoss from #{url}")
      return
    end
    system("tar", "xzf", dest, "-C", VENDOR_DIR)
    FileUtils.rm_f(dest)
  end

  ENV["MOSS_LIB_DIR"] = lib_dir if File.exist?(lib_file)
end

# --- validation harness -----------------------------------------------------

class Checks
  def initialize(scrubber)
    @scrubber = scrubber
    @failures = 0
  end

  def log(message)
    puts @scrubber.call(message)
  end

  def check(label, condition)
    if condition
      log("  ✓ #{label}")
    else
      @failures += 1
      log("  ✗ #{label}")
    end
  end

  attr_reader :failures
end

def run_validation(checks)
  require "moss"

  checks.log("Moss Ruby SDK — live validation")
  checks.log("• moss gem: v#{Moss::VERSION}")
  checks.log("• native runtime available: #{Moss.native_runtime_available?}")
  checks.check("libmoss loads and reports a version", !Moss.libmoss_version.nil?)
  checks.log("• libmoss C SDK: v#{Moss.libmoss_version}")

  client = Moss::Client.new(poll_interval_seconds: 2)
  index_name = "ruby-sdk-validate-#{Process.pid}-#{rand(100_000)}"
  checks.log("• index: #{index_name}")

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
    )
  ]

  begin
    checks.log("→ create_index (polls job to completion)…")
    create = client.create_index(index_name, documents)
    checks.check("create_index returned doc_count == 2", create.doc_count == 2)

    checks.log("→ get_index…")
    info = client.get_index(index_name)
    checks.check("get_index name matches", info.name == index_name)

    checks.log("→ load_index…")
    loaded = client.load_index(index_name)
    checks.check("load_index returned the index name", loaded == index_name)

    checks.log("→ local query…")
    result = client.query(index_name, "how long do refunds take?", top_k: 3)
    checks.check("query returned results", !result.docs.empty?)
    checks.check("top hit is the refunds doc", result.docs.first&.id == "doc-1")
    top = result.docs.first
    checks.log("    top: id=#{top&.id} score=#{format("%.4f", top&.score.to_f)} (#{result.time_taken_ms}ms)")

    checks.log("→ metadata-filtered query ($eq topic=shipping)…")
    filtered = client.query(
      index_name, "how long do refunds take?",
      top_k: 3, filter: { "field" => "topic", "condition" => { "$eq" => "shipping" } }
    )
    only_shipping = filtered.docs.all? { |d| d.metadata.nil? || d.metadata["topic"] == "shipping" }
    checks.check("filter restricted results to topic=shipping", only_shipping)

    checks.log("→ metadata-filtered query ($in topic in [shipping])…")
    in_filtered = client.query(
      index_name, "orders",
      top_k: 3, filter: { "field" => "topic", "condition" => { "$in" => ["shipping"] } }
    )
    in_only_shipping = in_filtered.docs.all? { |d| d.metadata.nil? || d.metadata["topic"] == "shipping" }
    checks.check("$in filter restricted results to topic=shipping", in_only_shipping)

    checks.log("→ get_documents…")
    fetched = client.get_documents(index_name)
    checks.check("get_documents returned stored docs", fetched.length >= 2)

    checks.log("→ list_indexes…")
    listed = client.list_indexes
    checks.check("list_indexes includes the new index", listed.any? { |i| i.name == index_name })

    validate_custom_embeddings(client, checks)
    validate_session(client, checks)
  ensure
    checks.log("→ cleanup (unload + delete_index)…")
    begin
      client.unload_index(index_name)
    rescue StandardError
      # ignore
    end
    begin
      deleted = client.delete_index(index_name)
      checks.check("delete_index reported success", deleted == true)
    rescue StandardError => e
      checks.log("  ! delete_index error: #{e.class}")
    end
    client.close
  end
end

def wait_for_job(client, job_id, timeout: 180)
  deadline = Process.clock_gettime(Process::CLOCK_MONOTONIC) + timeout
  loop do
    status = client.get_job_status(job_id)
    return status.status if %w[completed failed].include?(status.status)
    return "timeout" if Process.clock_gettime(Process::CLOCK_MONOTONIC) > deadline

    sleep 2
  end
end

def validate_custom_embeddings(client, checks)
  index_name = "ruby-sdk-custom-#{Process.pid}-#{rand(100_000)}"
  checks.log("→ custom embeddings: create #{index_name} (model inferred)…")
  documents = [
    Moss::DocumentInfo.new(id: "c-1", text: "first vector", embedding: [1.0, 0.0, 0.0, 0.0]),
    Moss::DocumentInfo.new(id: "c-2", text: "second vector", embedding: [0.0, 1.0, 0.0, 0.0]),
    Moss::DocumentInfo.new(id: "c-3", text: "third vector", embedding: [0.0, 0.0, 1.0, 0.0])
  ]

  begin
    client.create_index(index_name, documents)
    info = client.get_index(index_name)
    checks.check("custom index uses the custom model", info.model.id == Moss::Model::CUSTOM)

    client.load_index(index_name)
    result = client.query(index_name, "", embedding: [1.0, 0.0, 0.0, 0.0], top_k: 3)
    checks.check("embedding query returned results", !result.docs.empty?)
    checks.check("embedding query top hit is c-1", result.docs.first&.id == "c-1")
  ensure
    begin
      client.unload_index(index_name)
    rescue StandardError
      # ignore
    end
    begin
      client.delete_index(index_name)
    rescue StandardError
      # ignore
    end
  end
end

# Opens a session, or returns nil (logging a skip) when the account plan does
# not include sessions. Any non-plan error propagates.
def open_session_or_skip(client, session_index, checks)
  client.session(session_index)
rescue Moss::Core::NativeError, Moss::Error => e
  raise unless e.message.match?(/enterprise|plan not allowed/i)

  checks.log("  ⊘ sessions skipped (requires enterprise plan)")
  nil
end

def validate_session(client, checks)
  session_index = "ruby-sdk-session-#{Process.pid}-#{rand(100_000)}"
  checks.log("→ session: open #{session_index}…")
  session = open_session_or_skip(client, session_index, checks)
  return if session.nil?

  begin
    session.add_documents(
      [
        Moss::DocumentInfo.new(id: "s-1", text: "Cats are small domesticated carnivores.",
                               metadata: { "kind" => "cat" }),
        Moss::DocumentInfo.new(id: "s-2", text: "Dogs are loyal companion animals.",
                               metadata: { "kind" => "dog" })
      ]
    )
    checks.check("session doc_count == 2", session.doc_count == 2)

    sres = session.query("feline pet", top_k: 2)
    checks.check("session local query returned results", !sres.docs.empty?)
    checks.check("session top hit is the cat doc", sres.docs.first&.id == "s-1")

    fetched = session.get_documents(["s-1"])
    checks.check("session get_documents returns requested doc", fetched.first&.id == "s-1")

    checks.log("→ session: push_index to cloud…")
    push = session.push_index
    checks.check("session push_index returned a job id", !push.job_id.to_s.empty?)
    checks.log("    push job status: #{wait_for_job(client, push.job_id)}")
  ensure
    session.close
    begin
      client.unload_index(session_index)
    rescue StandardError
      # not necessarily loaded
    end
    begin
      client.delete_index(session_index)
    rescue StandardError
      # best-effort cleanup of the pushed index
    end
  end
end

# --- main -------------------------------------------------------------------

load_env_file(ENV_FILE)
scrubber = build_scrubber

if SECRET_KEYS.any? { |k| ENV[k].to_s.strip.empty? }
  warn scrubber.call("Missing credentials: ensure MOSS_PROJECT_ID and MOSS_PROJECT_KEY are set in #{ENV_FILE}")
  exit 2
end

checks = Checks.new(scrubber)
ensure_libmoss(->(m) { checks.log(m) })

begin
  run_validation(checks)
rescue StandardError => e
  # Scrub the message in case any credential value leaked into it.
  checks.log("FATAL: #{e.class}: #{scrubber.call(e.message)}")
  checks.log(scrubber.call(e.backtrace.first(5).join("\n")))
  exit 1
end

if checks.failures.zero?
  checks.log("\nAll checks passed ✅")
  exit 0
else
  checks.log("\n#{checks.failures} check(s) failed ❌")
  exit 1
end
