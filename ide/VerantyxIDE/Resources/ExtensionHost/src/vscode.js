"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.Workspace = exports.Window = void 0;
exports.createVSCodeAPI = createVSCodeAPI;
const rpc_1 = require("./rpc");
class Window {
    rpc;
    constructor(rpc) {
        this.rpc = rpc;
    }
    async showInformationMessage(message, ...items) {
        // Sends IPC to Swift frontend
        const response = await this.rpc.sendRequest('window.showInformationMessage', { message, items });
        return response;
    }
    async showErrorMessage(message, ...items) {
        const response = await this.rpc.sendRequest('window.showErrorMessage', { message, items });
        return response;
    }
}
exports.Window = Window;
class Workspace {
    rpc;
    constructor(rpc) {
        this.rpc = rpc;
    }
    get rootPath() {
        return process.cwd(); // simplified
    }
}
exports.Workspace = Workspace;
function createVSCodeAPI(rpc) {
    return {
        window: new Window(rpc),
        workspace: new Workspace(rpc),
        // other APIs like commands, languages, etc. would go here
    };
}
//# sourceMappingURL=vscode.js.map