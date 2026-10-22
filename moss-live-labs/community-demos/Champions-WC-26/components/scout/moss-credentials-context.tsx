"use client";

import { createContext, useContext, useMemo, useState } from "react";

type MossCredentials = {
  projectId: string;
  projectKey: string;
  setProjectId: (value: string) => void;
  setProjectKey: (value: string) => void;
  clearCredentials: () => void;
};

const MossCredentialsContext = createContext<MossCredentials | null>(null);

export function MossCredentialsProvider({ children }: { children: React.ReactNode }) {
  const [projectId, setProjectId] = useState("");
  const [projectKey, setProjectKey] = useState("");
  const value = useMemo(() => ({
    projectId,
    projectKey,
    setProjectId,
    setProjectKey,
    clearCredentials: () => {
      setProjectId("");
      setProjectKey("");
    },
  }), [projectId, projectKey]);
  return <MossCredentialsContext.Provider value={value}>{children}</MossCredentialsContext.Provider>;
}

export function useMossCredentials() {
  const value = useContext(MossCredentialsContext);
  if (!value) throw new Error("useMossCredentials must be used inside MossCredentialsProvider.");
  return value;
}
