export type MemoryZone = "front" | "near" | "mid" | "deep";

export interface MemoryEntry {
  name: string;
  zone: MemoryZone;
  path: string;
  size: number;
  modified: Date;
  version: number;
  frontmatter?: Record<string, string>;
}

export interface ReadMemoryResult {
    content: string;
    version: number;
    frontmatter?: Record<string, string>;
}

export interface EpisodicMemory {
    content: string;
    extractedAt: string;
    sources: string[];
    validity: {
        validFrom: string;
        validUntil?: string;
        conditions: string[];
        confidence: number;
    };
    conflictsWith?: string[];
}
