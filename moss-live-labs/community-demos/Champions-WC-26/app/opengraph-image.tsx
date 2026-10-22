import { ImageResponse } from "next/og";

export const alt = "Champions WC 26 — Build the XI. Chase the 8–0.";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default function OpenGraphImage() {
  return new ImageResponse(
    <div style={{ width: "100%", height: "100%", display: "flex", background: "#07111f", color: "#f3f7f5", padding: 72, position: "relative", fontFamily: "Arial" }}>
      <div style={{ position: "absolute", inset: 0, background: "radial-gradient(circle at 80% 30%, #17424e 0%, transparent 46%)" }} />
      <div style={{ width: 14, height: "100%", background: "#c8ff38", marginRight: 42 }} />
      <div style={{ display: "flex", flexDirection: "column", justifyContent: "space-between", zIndex: 1 }}>
        <div style={{ display: "flex", fontSize: 32, fontWeight: 800, letterSpacing: 3 }}>CHAMPIONS&nbsp;<span style={{ color: "#c8ff38" }}>(WC 26)</span></div>
        <div style={{ display: "flex", flexDirection: "column" }}><span style={{ fontSize: 66, fontWeight: 800 }}>BUILD THE XI.</span><span style={{ fontSize: 128, lineHeight: 1, fontWeight: 900, color: "#c8ff38" }}>CHASE 8–0.</span></div>
        <div style={{ fontSize: 24, color: "#9db0b8" }}>489 HISTORIC SQUADS · 48 TEAMS · ONE PERFECT RUN</div>
      </div>
      <div style={{ position: "absolute", right: 70, top: 66, width: 164, height: 164, border: "2px solid #c8ff38", borderRadius: 999, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 64, fontWeight: 900, color: "#c8ff38" }}>8–0</div>
    </div>,
    size,
  );
}
