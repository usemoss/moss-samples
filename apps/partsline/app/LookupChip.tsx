"use client";

import type { CSSProperties } from "react";

export type LookupChipResult =
  | "single"
  | "ambiguous"
  | "superseded"
  | "no_match";

export type LookupChipPayload = {
  filter: {
    year?: string;
    make?: string;
    model?: string;
    engine?: string;
    trim?: string;
  };
  result: LookupChipResult;
  parts: {
    part_number: string;
    name: string;
    price?: string;
    stock?: number;
  }[];
  candidates?: {
    attribute: string;
    values: string[];
  };
};

const RESULT_LABELS: Record<LookupChipResult, string> = {
  single: "Found",
  ambiguous: "Asking",
  superseded: "Replaced",
  no_match: "Not carried",
};

const SUPERSEDED_FLOW_LABEL = "old to new";

function formatVehicleFilter(chip: LookupChipPayload) {
  return [
    chip.filter.year,
    chip.filter.make,
    chip.filter.model,
    chip.filter.engine ? `${chip.filter.engine} engine` : "",
    chip.filter.trim,
  ]
    .filter(Boolean)
    .join(" ");
}

function formatCandidates(chip: LookupChipPayload) {
  const values = chip.candidates?.values ?? [];
  if (values.length === 0) {
    return "Needs more detail.";
  }

  return `Needs ${chip.candidates?.attribute ?? "detail"}: ${values.join(", ")}`;
}

function formatSupersededParts(chip: LookupChipPayload) {
  const [oldPart, replacementPart] = chip.parts;
  if (!oldPart || !replacementPart) {
    return SUPERSEDED_FLOW_LABEL;
  }

  return `${SUPERSEDED_FLOW_LABEL}: ${oldPart.part_number} to ${replacementPart.part_number}`;
}

export default function LookupChip({ chip }: { chip: LookupChipPayload }) {
  return (
    <div
      data-lookup-chip-result={chip.result}
      style={{
        ...styles.chip,
        ...resultStyles[chip.result],
      }}
    >
      <div style={styles.header}>
        <span style={styles.label}>{RESULT_LABELS[chip.result]}</span>
        <span style={styles.filter}>{formatVehicleFilter(chip)}</span>
      </div>

      {chip.result === "ambiguous" ? (
        <p style={styles.detail}>{formatCandidates(chip)}</p>
      ) : null}

      {chip.result === "superseded" ? (
        <p style={styles.detail}>{formatSupersededParts(chip)}</p>
      ) : null}

      {chip.result === "no_match" ? (
        <p style={styles.detail}>No match for this filtered vehicle.</p>
      ) : null}

      {chip.parts.length > 0 ? (
        <ul style={styles.parts}>
          {chip.parts.map((part) => (
            <li key={part.part_number} style={styles.part}>
              <span style={styles.partNumber}>{part.part_number}</span>
              <span>{part.name}</span>
              {part.price ? <span>${part.price}</span> : null}
              {part.stock !== undefined ? <span>Stock {part.stock}</span> : null}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

const styles = {
  chip: {
    display: "grid",
    gap: "10px",
    padding: "12px",
    border: "1px solid",
    borderRadius: "6px",
    fontSize: "14px",
    lineHeight: 1.35,
  },
  header: {
    display: "flex",
    flexWrap: "wrap",
    alignItems: "center",
    gap: "8px",
  },
  label: {
    padding: "4px 8px",
    borderRadius: "4px",
    background: "#ffffff",
    color: "#1f2b36",
    fontWeight: 700,
  },
  filter: {
    color: "#2b3c48",
    fontWeight: 700,
  },
  detail: {
    margin: 0,
    color: "#33434f",
  },
  parts: {
    display: "grid",
    gap: "6px",
    margin: 0,
    padding: 0,
    listStyle: "none",
  },
  part: {
    display: "flex",
    flexWrap: "wrap",
    gap: "8px",
  },
  partNumber: {
    fontWeight: 700,
  },
} satisfies Record<string, CSSProperties>;

const resultStyles = {
  single: {
    borderColor: "#8fc6a3",
    background: "#eef8f1",
  },
  ambiguous: {
    borderColor: "#d9b45f",
    background: "#fff8e8",
  },
  superseded: {
    borderColor: "#9fb4d8",
    background: "#f0f5ff",
  },
  no_match: {
    borderColor: "#d59292",
    background: "#fff0f0",
  },
} satisfies Record<LookupChipResult, CSSProperties>;
