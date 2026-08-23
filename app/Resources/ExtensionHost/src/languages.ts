import { RPCClient } from './rpc';
import { Disposable, Position, Range } from './types';
import { TextDocument } from './vscode'; // Assuming it's in vscode.ts

export class Languages {
    private rpc: RPCClient;
    private providers: Map<string, any> = new Map();
    private providerIdCounter = 0;

    constructor(rpc: RPCClient, private getDocument: (uri: string) => TextDocument | undefined) {
        this.rpc = rpc;
        
        // Listen for requests from Swift to invoke providers
        this.rpc.onNotification('languages.invokeProvider', async (params: { providerId: string, method: string, args: any, requestId: number }) => {
            const provider = this.providers.get(params.providerId);
            if (provider && typeof provider[params.method] === 'function') {
                try {
                    // Resolve Virtual Document
                    const doc = this.getDocument(params.args.uri);
                    if (!doc) throw new Error('Document not found');
                    
                    const position = new Position(params.args.position.line, params.args.position.character);
                    
                    const result = await Promise.resolve(provider[params.method](doc, position, { isCancellationRequested: false }));
                    this.rpc.sendNotification('languages.invokeProvider.response', { requestId: params.requestId, result });
                } catch (err: any) {
                    this.rpc.sendNotification('languages.invokeProvider.response', { requestId: params.requestId, error: err.toString() });
                }
            } else {
                this.rpc.sendNotification('languages.invokeProvider.response', { requestId: params.requestId, error: `Provider/method not found` });
            }
        });
    }

    public registerCompletionItemProvider(selector: any, provider: any, ...triggerCharacters: string[]): Disposable {
        return this.registerProvider('CompletionItemProvider', selector, provider, { triggerCharacters });
    }

    public registerHoverProvider(selector: any, provider: any): Disposable {
        return this.registerProvider('HoverProvider', selector, provider);
    }
    
    public registerDefinitionProvider(selector: any, provider: any): Disposable {
        return this.registerProvider('DefinitionProvider', selector, provider);
    }

    private registerProvider(type: string, selector: any, provider: any, extraOptions?: any): Disposable {
        const id = `${type}-${this.providerIdCounter++}`;
        this.providers.set(id, provider);
        
        // Notify Swift that a new language provider is available for the given selector
        this.rpc.sendNotification('languages.registerProvider', {
            id,
            type,
            selector,
            options: extraOptions
        });
        
        return new Disposable(() => {
            this.providers.delete(id);
            this.rpc.sendNotification('languages.unregisterProvider', { id });
        });
    }
}
