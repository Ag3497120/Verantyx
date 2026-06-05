export type MemoryZone = "front" | "near" | "mid" | "deep";

export interface MemoryFrontmatter extends Record<string, string> {
  status?: "pending" | "approved" | "rejected" | string;
  confidence?: "high" | "low" | string;
}

export interface MemoryEntry {
  name: string;
  zone: MemoryZone;
  path: string;
  size: number;
  modified: Date;
  version: number;
  frontmatter?: MemoryFrontmatter;
}

export interface ReadMemoryResult {
    content: string;
    version: number;
    frontmatter?: MemoryFrontmatter;
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
