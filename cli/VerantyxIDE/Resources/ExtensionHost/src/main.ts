import { RPCClient } from './rpc';
import { createVSCodeAPI } from './vscode';
import * as path from 'path';
import * as Module from 'module';

// Create the IPC connection to Swift
const rpc = new RPCClient();

// Create the shimmed vscode API
const vscodeAPI = createVSCodeAPI(rpc);

// -----------------------------------------------------------------------------
// Magic: Intercept module loading to inject our fake 'vscode' module
// When an extension does `require('vscode')`, they get our shim.
// -----------------------------------------------------------------------------
const originalRequire = Module.prototype.require;

(Module.prototype as any).require = function(request: string) {
    if (request === 'vscode') {
        return vscodeAPI;
    }
    // Fallback to normal require for everything else
    return originalRequire.apply(this, arguments as any);
};

// Notify Swift that the Extension Host is ready
rpc.sendNotification('host.ready', { version: '1.0.0' });

// Listen for extension load requests from Swift (VSIXPackageManager)
rpc.onNotification('extension.load', (params: any) => {
    try {
        const ext = require(params.main);
        if (ext && ext.activate) {
            // Provide a fake context
            const context = { subscriptions: [] };
            ext.activate(context);
            rpc.sendNotification('extension.loaded', { id: params.id, success: true });
        }
    } catch (e: any) {
        rpc.sendNotification('extension.loaded', { id: params.id, success: false, error: e.toString() });
    }
});

// Keep the process alive
setInterval(() => {}, 1000 * 60 * 60);
