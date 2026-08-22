import { RPCClient } from './rpc';
export declare class Window {
    private rpc;
    constructor(rpc: RPCClient);
    showInformationMessage(message: string, ...items: string[]): Promise<string | undefined>;
    showErrorMessage(message: string, ...items: string[]): Promise<string | undefined>;
}
export declare class Workspace {
    private rpc;
    constructor(rpc: RPCClient);
    get rootPath(): string | undefined;
}
export declare function createVSCodeAPI(rpc: RPCClient): {
    window: Window;
    workspace: Workspace;
};
//# sourceMappingURL=vscode.d.ts.map