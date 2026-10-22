defmodule Moss.Application do
  @moduledoc false

  use Application

  @impl true
  def start(_type, _args) do
    Supervisor.start_link([Moss.Inference.Pool], strategy: :one_for_one, name: Moss.Supervisor)
  end
end
