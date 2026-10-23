import { CopilotRuntime, OpenAIAdapter, copilotRuntimeNextJSAppRouterEndpoint } from "@copilotkit/runtime";
import { NextRequest, NextResponse } from "next/server";
import OpenAI from "openai";

export const POST = async (req: NextRequest) => {
  const apiKey = process.env.OPENAI_API_KEY;

  if (!apiKey || apiKey === "your_openai_api_key") {
    // If OpenAI API key is missing, return a helpful error indicating it must be set.
    return new NextResponse(
      JSON.stringify({
        error: "OPENAI_API_KEY is not configured. Please set it in your environment variables to allow CopilotKit to communicate with the LLM.",
      }),
      {
        status: 400,
        headers: { "content-type": "application/json" },
      }
    );
  }

  try {
    const openai = new OpenAI({ apiKey });
    const serviceAdapter = new OpenAIAdapter({ openai });
    const runtime = new CopilotRuntime();

    const { handleRequest } = copilotRuntimeNextJSAppRouterEndpoint({
      runtime,
      serviceAdapter,
      endpoint: "/api/copilotkit",
    });

    return handleRequest(req);
  } catch (error: any) {
    console.error("CopilotKit runtime initialization failed:", error);
    return new NextResponse(
      JSON.stringify({
        error: error.message || "Failed to handle CopilotKit runtime request",
      }),
      {
        status: 500,
        headers: { "content-type": "application/json" },
      }
    );
  }
};
