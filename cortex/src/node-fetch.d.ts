// Shim for node-fetch — suppresses TS7016 until @types/node-fetch is installed.
// The actual runtime import works fine; this just tells tsc the module exists.
declare module "node-fetch" {
  const fetch: (url: string, init?: Record<string, unknown>) => Promise<{
    json: () => Promise<unknown>;
    text: () => Promise<string>;
    ok: boolean;
    status: number;
  }>;
  export default fetch;
}
