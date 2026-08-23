import { RPCClient } from './rpc';
import { Disposable } from './types';

export class Commands {
    private rpc: RPCClient;
    private localCommands: Map<string, (...args: any[]) => any> = new Map();

    constructor(rpc: RPCClient) {
        this.rpc = rpc;
        
        // Listen for requests from Swift to execute a locally registered command
        this.rpc.onNotification('commands.executeLocalCommand', async (params: { command: string, args: any[], requestId: number }) => {
            const handler = this.localCommands.get(params.command);
            if (handler) {
                try {
                    const result = await Promise.resolve(handler(...(params.args || [])));
                    this.rpc.sendNotification('commands.executeLocalCommand.response', { requestId: params.requestId, result });
                } catch (err: any) {
                    this.rpc.sendNotification('commands.executeLocalCommand.response', { requestId: params.requestId, error: err.toString() });
                }
            } else {
                this.rpc.sendNotification('commands.executeLocalCommand.response', { requestId: params.requestId, error: `Command ${params.command} not found` });
            }
        });
    }

    public registerCommand(command: string, callback: (...args: any[]) => any, thisArg?: any): Disposable {
        const boundCallback = thisArg ? callback.bind(thisArg) : callback;
        this.localCommands.set(command, boundCallback);
        
        // Notify Swift that this command is available
        this.rpc.sendNotification('commands.registerCommand', { command });
        
        return new Disposable(() => {
            this.localCommands.delete(command);
            this.rpc.sendNotification('commands.unregisterCommand', { command });
        });
    }

    public async executeCommand<T>(command: string, ...rest: any[]): Promise<T | undefined> {
        // If it's a local command, execute it directly
        if (this.localCommands.has(command)) {
            const handler = this.localCommands.get(command)!;
            return await Promise.resolve(handler(...rest));
        }
        
        // Otherwise, it might be a built-in VS Code command implemented in Swift
        const result = await this.rpc.sendRequest('commands.executeCommand', { command, args: rest });
        return result as T;
    }
}
