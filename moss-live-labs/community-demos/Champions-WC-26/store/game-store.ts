"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";
import type {
  DraftPick,
  DraftPlayer,
  ClassicRatingMode,
  FormationName,
  GameMode,
  HistoricSquad,
  MossReplacement,
  SquadDnaResult,
  TournamentResult,
} from "../lib/types";

export type GamePhase = "mode" | "setup" | "classic-ratings" | "draft" | "era-spin" | "era-draft" | "scout" | "dna" | "entry" | "simulation";

type GameState = {
  gameMode: GameMode;
  classicRatingMode: ClassicRatingMode;
  formation: FormationName;
  phase: GamePhase;
  picks: DraftPick[];
  currentSquad: HistoricSquad | null;
  usedSquads: string[];
  eraYear: number | null;
  usedEraYears: number[];
  scoutReplacement: MossReplacement | null;
  squadDna: SquadDnaResult | null;
  result: TournamentResult | null;
  chooseMode: (mode: GameMode) => void;
  backToModes: () => void;
  setFormation: (formation: FormationName) => void;
  beginDraft: () => void;
  chooseClassicRatingMode: (mode: ClassicRatingMode) => void;
  setCurrentSquad: (squad: HistoricSquad | null) => void;
  setEraYear: (year: number) => void;
  assignPlayer: (player: DraftPlayer, slotId: string) => void;
  assignEraPlayer: (player: DraftPlayer, slotId: string) => void;
  removePick: (slotId: string) => void;
  openScout: () => void;
  skipScout: () => void;
  applyScoutReplacement: (player: DraftPlayer, slotId: string) => void;
  setSquadDna: (result: SquadDnaResult) => void;
  finishDna: () => void;
  skipDna: () => void;
  beginSimulation: () => void;
  returnToEntry: () => void;
  setResult: (result: TournamentResult) => void;
  reset: () => void;
};

const freshGame = (gameMode: GameMode, phase: GamePhase = "setup") => ({
  gameMode,
  classicRatingMode: "campaign" as ClassicRatingMode,
  formation: "4-3-3" as FormationName,
  phase,
  picks: [] as DraftPick[],
  currentSquad: null,
  usedSquads: [] as string[],
  eraYear: null,
  usedEraYears: [] as number[],
  scoutReplacement: null,
  squadDna: null,
  result: null,
});

export const useGameStore = create<GameState>()(
  persist(
    (set, get) => ({
      ...freshGame("classic", "mode"),
      chooseMode: (gameMode) => set(freshGame(gameMode)),
      backToModes: () => set(freshGame("classic", "mode")),
      setFormation: (formation) => set((state) => ({
        ...freshGame(state.gameMode),
        formation,
      })),
      beginDraft: () => set((state) => ({ phase: state.gameMode === "era" ? "era-spin" : "classic-ratings" })),
      chooseClassicRatingMode: (classicRatingMode) => set((state) => state.gameMode === "classic"
        ? { classicRatingMode, phase: "draft", picks: [], currentSquad: null, usedSquads: [], scoutReplacement: null, squadDna: null, result: null }
        : state),
      setCurrentSquad: (currentSquad) => set({ currentSquad }),
      setEraYear: (eraYear) => set((state) => state.gameMode === "era"
        && !state.usedEraYears.includes(eraYear)
        ? { eraYear, phase: "era-draft", currentSquad: null, squadDna: null, result: null }
        : state),
      assignPlayer: (player, slotId) => {
        const state = get();
        if (state.gameMode !== "classic" || !state.currentSquad || state.picks.some((pick) => pick.slotId === slotId)) return;
        const picks = [...state.picks, { player, slotId, squadId: state.currentSquad.id }];
        set({
          picks,
          usedSquads: [...state.usedSquads, state.currentSquad.id],
          currentSquad: null,
          phase: picks.length === 11 ? "scout" : "draft",
          squadDna: null,
        });
      },
      assignEraPlayer: (player, slotId) => {
        const state = get();
        if (state.gameMode !== "era" || player.year !== state.eraYear || state.picks.some((pick) => pick.slotId === slotId || pick.player.id === player.id)) return;
        const picks = [...state.picks, { player, slotId, squadId: `${player.nationCode}-${player.year}` }];
        set({
          picks,
          eraYear: null,
          usedEraYears: [...state.usedEraYears, state.eraYear],
          phase: picks.length === 11 ? "dna" : "era-spin",
          squadDna: null,
        });
      },
      removePick: (slotId) => set((state) => ({
        picks: state.picks.filter((pick) => pick.slotId !== slotId),
        squadDna: null,
      })),
      openScout: () => set((state) => state.gameMode === "classic" && state.phase === "entry" && !state.scoutReplacement && state.picks.length === 11
        ? { phase: "scout", squadDna: null }
        : state),
      skipScout: () => set((state) => state.phase === "scout" ? { phase: state.squadDna ? "entry" : "dna" } : state),
      applyScoutReplacement: (player, slotId) => {
        const state = get();
        if (state.gameMode !== "classic" || state.phase !== "scout" || state.scoutReplacement || state.picks.some((pick) => pick.player.id === player.id)) return;
        const outgoing = state.picks.find((pick) => pick.slotId === slotId);
        if (!outgoing || outgoing.player.position !== player.position) return;
        const picks = state.picks.map((pick) => pick.slotId === slotId
          ? { player, slotId, squadId: `moss:${player.id}` }
          : pick);
        set({
          picks,
          phase: "dna",
          squadDna: null,
          scoutReplacement: {
            outgoing: outgoing.player,
            incoming: player,
            slotId,
            completedAt: new Date().toISOString(),
          },
        });
      },
      setSquadDna: (squadDna) => set({ squadDna }),
      finishDna: () => set((state) => state.phase === "dna" && state.squadDna ? { phase: "entry" } : state),
      skipDna: () => set((state) => state.phase === "dna" ? { phase: "entry" } : state),
      beginSimulation: () => set({ phase: "simulation" }),
      returnToEntry: () => set({ phase: "entry" }),
      setResult: (result) => set({ result }),
      reset: () => set((state) => freshGame(state.gameMode)),
    }),
    {
      name: "champions-wc26-game",
      version: 4,
      migrate: (persisted) => {
        const state = persisted as Partial<GameState>;
        if (state.gameMode === "era" && !Array.isArray(state.usedEraYears)) return freshGame("era");
        const emptyLegacyGame = (!state.picks || state.picks.length === 0) && state.phase === "setup";
        return {
          ...freshGame(state.gameMode ?? "classic", emptyLegacyGame ? "mode" : (state.phase ?? "mode")),
          ...state,
          phase: emptyLegacyGame ? "mode" : (state.phase ?? "mode"),
          gameMode: state.gameMode ?? "classic",
          classicRatingMode: state.classicRatingMode ?? "campaign",
          eraYear: state.eraYear ?? null,
          usedEraYears: state.usedEraYears ?? [],
          squadDna: state.squadDna ?? null,
        };
      },
      partialize: (state) => ({
        gameMode: state.gameMode,
        classicRatingMode: state.classicRatingMode,
        formation: state.formation,
        phase: state.phase,
        picks: state.picks,
        currentSquad: state.currentSquad,
        usedSquads: state.usedSquads,
        eraYear: state.eraYear,
        usedEraYears: state.usedEraYears,
        scoutReplacement: state.scoutReplacement,
        squadDna: state.squadDna,
        result: state.result,
      }),
    },
  ),
);
