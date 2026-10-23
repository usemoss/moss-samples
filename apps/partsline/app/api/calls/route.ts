import { listCallLogRows } from "../../calls/callLog";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  const calls = listCallLogRows();
  return Response.json({ calls });
}
