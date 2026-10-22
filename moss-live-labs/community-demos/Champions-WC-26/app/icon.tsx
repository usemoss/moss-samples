import { ImageResponse } from "next/og";

export const size = { width: 64, height: 64 };
export const contentType = "image/png";

export default function Icon() {
  return new ImageResponse(<div style={{ width: 64, height: 64, background: "#c8ff38", color: "#06111d", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 32, fontWeight: 900, borderRadius: 16 }}>8</div>, size);
}
