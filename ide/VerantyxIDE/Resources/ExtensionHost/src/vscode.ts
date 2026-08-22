import { RPCClient } from './rpc';
import { EventEmitter } from 'events';
import { Disposable, Position, Range, Location, Uri } from './types';
import { Commands } from './commands';
import { Languages } from './languages';
import { WindowExt } from './window';
import { FileSystem } from './workspace_fs';

// -----------------------------------------------------------------------------
// Utilities: Event API emulation
// -----------------------------------------------------------------------------
export interface Event<T> {
    (listener: (e: T) => any, thisArgs?: any, disposables?: any[]): { dispose(): void };
}

export class EventEmitterImpl<T> {
    private emitter = new EventEmitter();

    public get event(): Event<T> {
        return (listener: (e: T) => any, thisArgs?: any, disposables?: any[]) => {
            const boundListener = thisArgs ? listener.bind(thisArgs) : listener;
            this.emitter.on('event', boundListener);
            const disposable = {
                dispose: () => {
                    this.emitter.removeListener('event', boundListener);
                }
            };
            if (disposables) {
                disposables.push(disposable);
            }
            return disposable;
        };
    }

    public fire(data: T): void {
        this.emitter.emit('event', data);
    }
}

// -----------------------------------------------------------------------------
// Text Document Emulation
// -----------------------------------------------------------------------------
export class TextDocument {
    public readonly uri: any;
    public readonly fileName: string;
    public readonly languageId: string;
    public readonly version: number;
    public readonly isDirty: boolean;
    public readonly isClosed: boolean;
    
    private lines: string[];

    constructor(uri: string, languageId: string, version: number, content: string) {
        this.uri = { fsPath: uri, toString: () => uri };
        this.fileName = uri;
        this.languageId = languageId;
        this.version = version;
        this.isDirty = false;
        this.isClosed = false;
        this.lines = content.split('\n');
    }

    public getText(): string {
        return this.lines.join('\n');
    }

    public applyChange(range: { startLine: number, endLine: number }, newText: string) {
        // Enterprise robustness: apply minimal range edits to the virtual document
        // In a real scenario, this involves column-level ranges. For now, we do line-level.
        const newLines = newText.split('\n');
        this.lines.splice(range.startLine, range.endLine - range.startLine + 1, ...newLines);
        // version would increment here ideally
    }
}

// -----------------------------------------------------------------------------
// Webview Emulation
// -----------------------------------------------------------------------------
export class Webview {
    private rpc: RPCClient;
    public readonly panelId: string;
    private _html: string = '';

    private _onDidReceiveMessage = new EventEmitterImpl<any>();
    public readonly onDidReceiveMessage = this._onDidReceiveMessage.event;

    constructor(rpc: RPCClient, panelId: string) {
        this.rpc = rpc;
        this.panelId = panelId;

        // Listen for messages from the Swift Webview to the extension
        this.rpc.onNotification(`webview.onDidReceiveMessage.${panelId}`, (message: any) => {
            this._onDidReceiveMessage.fire(message);
        });
    }

    public get html(): string {
        return this._html;
    }

    public set html(value: string) {
        this._html = value;
        // Send the updated HTML to Swift
        this.rpc.sendNotification('webview.updateHTML', { panelId: this.panelId, html: value });
    }

    public async postMessage(message: any): Promise<boolean> {
        await this.rpc.sendRequest('webview.postMessage', { panelId: this.panelId, message });
        return true;
    }
}

export class WebviewPanel {
    public readonly webview: Webview;
    public title: string;
    
    private _onDidDispose = new EventEmitterImpl<void>();
    public readonly onDidDispose = this._onDidDispose.event;

    constructor(rpc: RPCClient, panelId: string, title: string) {
        this.title = title;
        this.webview = new Webview(rpc, panelId);

        rpc.onNotification(`webview.onDidDispose.${panelId}`, () => {
            this._onDidDispose.fire();
        });
    }

    public dispose() {
        this.webview['rpc'].sendNotification('webview.dispose', { panelId: this.webview.panelId });
        this._onDidDispose.fire();
    }
}

// -----------------------------------------------------------------------------
// VS Code Namespaces
// -----------------------------------------------------------------------------
export class Window {
    private rpc: RPCClient;
    private ext: WindowExt;

    constructor(rpc: RPCClient) {
        this.rpc = rpc;
        this.ext = new WindowExt(rpc);
    }

    public createOutputChannel(name: string) {
        return this.ext.createOutputChannel(name);
    }

    public showQuickPick(items: any[], options?: any) {
        return this.ext.showQuickPick(items, options);
    }

    public showInputBox(options?: any) {
        return this.ext.showInputBox(options);
    }

    public createWebviewPanel(viewType: string, title: string, showOptions: any, options?: any): WebviewPanel {
        // Generate a unique ID for this panel instance
        const panelId = `${viewType}-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
        
        // Instruct Swift to open a WKWebView native panel
        this.rpc.sendNotification('window.createWebviewPanel', {
            panelId,
            viewType,
            title,
            showOptions,
            options
        });

        return new WebviewPanel(this.rpc, panelId, title);
    }

    public async showInformationMessage(message: string, ...items: string[]): Promise<string | undefined> {
        const response = await this.rpc.sendRequest('window.showInformationMessage', { message, items });
        return response as string | undefined;
    }

    public async showErrorMessage(message: string, ...items: string[]): Promise<string | undefined> {
        const response = await this.rpc.sendRequest('window.showErrorMessage', { message, items });
        return response as string | undefined;
    }
}

export class Workspace {
    private rpc: RPCClient;
    public textDocuments: TextDocument[] = [];
    public fs: FileSystem;
    
    // Events
    private _onDidChangeTextDocument = new EventEmitterImpl<any>();
    public readonly onDidChangeTextDocument = this._onDidChangeTextDocument.event;
    
    private _onDidOpenTextDocument = new EventEmitterImpl<TextDocument>();
    public readonly onDidOpenTextDocument = this._onDidOpenTextDocument.event;

    constructor(rpc: RPCClient) {
        this.rpc = rpc;
        this.fs = new FileSystem(rpc);

        // Listen for IPC messages from Swift to sync the virtual text documents
        this.rpc.onNotification('workspace.didOpenTextDocument', (params: any) => {
            const doc = new TextDocument(params.uri, params.languageId, params.version, params.text);
            this.textDocuments.push(doc);
            this._onDidOpenTextDocument.fire(doc);
        });

        this.rpc.onNotification('workspace.didChangeTextDocument', (params: any) => {
            const doc = this.textDocuments.find(d => d.fileName === params.uri);
            if (doc) {
                doc.applyChange(params.range, params.text);
                // Fire the event so extensions know about the change
                this._onDidChangeTextDocument.fire({
                    document: doc,
                    contentChanges: [{ range: params.range, text: params.text }]
                });
            }
        });
        
        this.rpc.onNotification('workspace.didCloseTextDocument', (params: any) => {
            this.textDocuments = this.textDocuments.filter(d => d.fileName !== params.uri);
        });
    }

    public get rootPath(): string | undefined {
        return process.cwd();
    }

    public getConfiguration(section?: string): any {
        // Simple mock for now
        return {
            get: (key: string, defaultValue?: any) => defaultValue,
            update: async (key: string, value: any) => {
                await this.rpc.sendRequest('workspace.getConfiguration.update', { section, key, value });
            }
        };
    }
}

export function createVSCodeAPI(rpc: RPCClient) {
    const workspaceObj = new Workspace(rpc);
    
    return {
        window: new Window(rpc),
        workspace: workspaceObj,
        commands: new Commands(rpc),
        languages: new Languages(rpc, (uri: string) => workspaceObj.textDocuments.find(d => d.fileName === uri)),
        EventEmitter: EventEmitterImpl,
        Disposable,
        Position,
        Range,
        Location,
        Uri
    };
}
