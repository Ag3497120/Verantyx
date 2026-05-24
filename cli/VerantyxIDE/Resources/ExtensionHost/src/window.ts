import { RPCClient } from './rpc';
import { EventEmitterImpl, WebviewPanel } from './vscode'; // Assuming WebviewPanel is still exported from vscode.ts or we'll move it
import { Disposable } from './types';

export class OutputChannel {
    public readonly name: string;
    private rpc: RPCClient;

    constructor(name: string, rpc: RPCClient) {
        this.name = name;
        this.rpc = rpc;
        this.rpc.sendNotification('window.createOutputChannel', { name });
    }

    append(value: string): void {
        this.rpc.sendNotification('window.outputChannel.append', { name: this.name, value });
    }

    appendLine(value: string): void {
        this.rpc.sendNotification('window.outputChannel.appendLine', { name: this.name, value });
    }

    clear(): void {
        this.rpc.sendNotification('window.outputChannel.clear', { name: this.name });
    }

    show(preserveFocus?: boolean): void {
        this.rpc.sendNotification('window.outputChannel.show', { name: this.name, preserveFocus });
    }

    hide(): void {
        this.rpc.sendNotification('window.outputChannel.hide', { name: this.name });
    }

    dispose(): void {
        this.rpc.sendNotification('window.outputChannel.dispose', { name: this.name });
    }
}

export class WindowExt {
    private rpc: RPCClient;

    constructor(rpc: RPCClient) {
        this.rpc = rpc;
    }

    public createOutputChannel(name: string): OutputChannel {
        return new OutputChannel(name, this.rpc);
    }

    public async showQuickPick(items: string[] | any[], options?: any): Promise<any> {
        return await this.rpc.sendRequest('window.showQuickPick', { items, options });
    }

    public async showInputBox(options?: any): Promise<string | undefined> {
        return await this.rpc.sendRequest('window.showInputBox', { options });
    }
}
