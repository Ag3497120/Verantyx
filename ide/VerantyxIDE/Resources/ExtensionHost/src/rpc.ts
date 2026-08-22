import * as readline from 'readline';

export class RPCClient {
    private requestIDCounter = 0;
    private pendingRequests: Map<number, (result: any) => void> = new Map();
    private notificationListeners: Map<string, (params: any) => void> = new Map();

    constructor() {
        const rl = readline.createInterface({
            input: process.stdin,
            output: process.stdout,
            terminal: false
        });

        rl.on('line', (line) => {
            if (!line.trim()) return;
            try {
                const msg = JSON.parse(line);
                this.handleMessage(msg);
            } catch (e) {
                console.error('Failed to parse RPC message:', e);
            }
        });
    }

    private handleMessage(msg: any) {
        if (msg.id !== undefined && (msg.result !== undefined || msg.error !== undefined)) {
            // It's a response
            const resolve = this.pendingRequests.get(msg.id);
            if (resolve) {
                resolve(msg.result);
                this.pendingRequests.delete(msg.id);
            }
        } else if (msg.method) {
            // It's a request from Swift
            this.handleRequestFromSwift(msg);
        }
    }

    private async handleRequestFromSwift(msg: any) {
        if (msg.id === undefined) {
            // It's a notification from Swift
            const listener = this.notificationListeners.get(msg.method);
            if (listener) {
                listener(msg.params);
            }
            return;
        }

        // Handle calls from Swift to the extension host (e.g. extension activate request)
        if (msg.method === 'extension.activate') {
            this.sendResponse(msg.id, { success: true });
        }
    }

    public onNotification(method: string, listener: (params: any) => void) {
        this.notificationListeners.set(method, listener);
    }

    public sendNotification(method: string, params: any = {}) {
        const payload = JSON.stringify({
            jsonrpc: '2.0',
            method,
            params
        });
        process.stdout.write(payload + '\n');
    }

    public sendRequest(method: string, params: any = {}): Promise<any> {
        return new Promise((resolve) => {
            const id = this.requestIDCounter++;
            this.pendingRequests.set(id, resolve);
            
            const payload = JSON.stringify({
                jsonrpc: '2.0',
                id,
                method,
                params
            });
            process.stdout.write(payload + '\n');
        });
    }

    private sendResponse(id: number, result: any) {
        const payload = JSON.stringify({
            jsonrpc: '2.0',
            id,
            result
        });
        process.stdout.write(payload + '\n');
    }
}
