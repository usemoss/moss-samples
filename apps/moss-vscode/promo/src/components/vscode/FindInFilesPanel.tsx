import { vscode } from "../../lib/colors";

export type GrepResult = {
  file: string;
  line: number;
  preview: string;
};

type FindInFilesPanelProps = {
  query: string;
  results: GrepResult[];
  showResults?: boolean;
  selectedIndex?: number | null;
};

export const FindInFilesPanel: React.FC<FindInFilesPanelProps> = ({
  query,
  results,
  showResults = false,
  selectedIndex = null,
}) => (
  <div
    style={{
      width: 280,
      background: vscode.sidebar,
      display: "flex",
      flexDirection: "column",
      flexShrink: 0,
      borderRight: `1px solid ${vscode.border}`,
      overflow: "hidden",
      fontFamily: "-apple-system, BlinkMacSystemFont, system-ui, sans-serif",
    }}
  >
    <div
      style={{
        padding: "10px 14px 6px",
        fontSize: 11,
        fontWeight: 600,
        letterSpacing: 0.6,
        color: "#bbbbbb",
        textTransform: "uppercase",
      }}
    >
      Search
    </div>
    <div style={{ padding: "4px 12px 10px" }}>
      <div
        style={{
          background: vscode.inputBg,
          border: "1px solid #007acc",
          borderRadius: 2,
          padding: "6px 8px",
          fontSize: 13,
          color: "#ffffff",
          minHeight: 28,
          display: "flex",
          alignItems: "center",
          fontFamily: '"SF Mono", Menlo, Monaco, monospace',
        }}
      >
        {query}
        <span
          style={{
            width: 1,
            height: 14,
            background: "#ffffff",
            marginLeft: 1,
            opacity: 0.9,
          }}
        />
      </div>
      <div style={{ marginTop: 8, fontSize: 11, color: "#858585" }}>
        files to include
      </div>
      <div
        style={{
          marginTop: 4,
          background: "#3c3c3c",
          borderRadius: 2,
          padding: "5px 8px",
          fontSize: 12,
          color: "#cccccc",
        }}
      >
        {"**/*.{ts,tsx,js,md}"}
      </div>
    </div>

    {showResults && (
      <div style={{ flex: 1, overflow: "hidden", paddingBottom: 8 }}>
        <div
          style={{
            padding: "6px 14px",
            fontSize: 11,
            color: "#858585",
          }}
        >
          {results.length} results in {results.length} files
        </div>
        {results.map((r, i) => (
          <div
            key={`${r.file}-${r.line}`}
            style={{
              padding: "6px 14px",
              background:
                selectedIndex === i ? vscode.listActive : "transparent",
              borderLeft:
                selectedIndex === i
                  ? "2px solid #007acc"
                  : "2px solid transparent",
            }}
          >
            <div
              style={{
                fontSize: 12,
                color: "#cccccc",
                fontWeight: 500,
                marginBottom: 2,
              }}
            >
              {r.file}
              <span style={{ color: "#858585", fontWeight: 400 }}>
                {":"}
                {r.line}
              </span>
            </div>
            <div
              style={{
                fontSize: 11,
                color: "#9d9d9d",
                fontFamily: '"SF Mono", Menlo, Monaco, monospace',
                whiteSpace: "nowrap",
                overflow: "hidden",
                textOverflow: "ellipsis",
              }}
            >
              {r.preview}
            </div>
          </div>
        ))}
      </div>
    )}
  </div>
);
