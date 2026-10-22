import type { FormationName, FormationSlot } from "./types";

export const FORMATIONS: Record<FormationName, FormationSlot[]> = {
  "4-3-3": [
    { id: "gk", label: "GK", position: "GK", x: 50, y: 89 },
    { id: "lb", label: "LB", position: "DEF", x: 16, y: 70 },
    { id: "lcb", label: "CB", position: "DEF", x: 38, y: 75 },
    { id: "rcb", label: "CB", position: "DEF", x: 62, y: 75 },
    { id: "rb", label: "RB", position: "DEF", x: 84, y: 70 },
    { id: "lcm", label: "CM", position: "MID", x: 28, y: 48 },
    { id: "cm", label: "CM", position: "MID", x: 50, y: 56 },
    { id: "rcm", label: "CM", position: "MID", x: 72, y: 48 },
    { id: "lw", label: "LW", position: "FWD", x: 20, y: 20 },
    { id: "st", label: "ST", position: "FWD", x: 50, y: 13 },
    { id: "rw", label: "RW", position: "FWD", x: 80, y: 20 },
  ],
  "4-4-2": [
    { id: "gk", label: "GK", position: "GK", x: 50, y: 89 },
    { id: "lb", label: "LB", position: "DEF", x: 16, y: 70 },
    { id: "lcb", label: "CB", position: "DEF", x: 38, y: 75 },
    { id: "rcb", label: "CB", position: "DEF", x: 62, y: 75 },
    { id: "rb", label: "RB", position: "DEF", x: 84, y: 70 },
    { id: "lm", label: "LM", position: "MID", x: 15, y: 43 },
    { id: "lcm", label: "CM", position: "MID", x: 39, y: 51 },
    { id: "rcm", label: "CM", position: "MID", x: 61, y: 51 },
    { id: "rm", label: "RM", position: "MID", x: 85, y: 43 },
    { id: "ls", label: "ST", position: "FWD", x: 36, y: 17 },
    { id: "rs", label: "ST", position: "FWD", x: 64, y: 17 },
  ],
  "3-5-2": [
    { id: "gk", label: "GK", position: "GK", x: 50, y: 89 },
    { id: "lcb", label: "CB", position: "DEF", x: 25, y: 72 },
    { id: "cb", label: "CB", position: "DEF", x: 50, y: 77 },
    { id: "rcb", label: "CB", position: "DEF", x: 75, y: 72 },
    { id: "lwb", label: "LWB", position: "MID", x: 12, y: 44 },
    { id: "lcm", label: "CM", position: "MID", x: 33, y: 51 },
    { id: "cam", label: "CAM", position: "MID", x: 50, y: 37 },
    { id: "rcm", label: "CM", position: "MID", x: 67, y: 51 },
    { id: "rwb", label: "RWB", position: "MID", x: 88, y: 44 },
    { id: "ls", label: "ST", position: "FWD", x: 36, y: 15 },
    { id: "rs", label: "ST", position: "FWD", x: 64, y: 15 },
  ],
};

export const FORMATION_MODIFIERS: Record<FormationName, { attack: number; defense: number }> = {
  "4-3-3": { attack: 3, defense: 0 },
  "4-4-2": { attack: 0, defense: 2 },
  "3-5-2": { attack: 2, defense: -2 },
};
