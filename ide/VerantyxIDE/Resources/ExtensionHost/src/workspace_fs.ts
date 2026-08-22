import { RPCClient } from './rpc';
import { Uri } from './types';

export class FileSystem {
    private rpc: RPCClient;

    constructor(rpc: RPCClient) {
        this.rpc = rpc;
    }

    public async stat(uri: Uri): Promise<any> {
        return await this.rpc.sendRequest('workspace.fs.stat', { uri: uri.toString() });
    }

    public async readDirectory(uri: Uri): Promise<[string, any][]> {
        return await this.rpc.sendRequest('workspace.fs.readDirectory', { uri: uri.toString() });
    }

    public async createDirectory(uri: Uri): Promise<void> {
        await this.rpc.sendRequest('workspace.fs.createDirectory', { uri: uri.toString() });
    }

    public async readFile(uri: Uri): Promise<Uint8Array> {
        const base64: string = await this.rpc.sendRequest('workspace.fs.readFile', { uri: uri.toString() });
        return Buffer.from(base64, 'base64');
    }

    public async writeFile(uri: Uri, content: Uint8Array): Promise<void> {
        const base64 = Buffer.from(content).toString('base64');
        await this.rpc.sendRequest('workspace.fs.writeFile', { uri: uri.toString(), content: base64 });
    }

    public async delete(uri: Uri, options?: { recursive?: boolean, useTrash?: boolean }): Promise<void> {
        await this.rpc.sendRequest('workspace.fs.delete', { uri: uri.toString(), options });
    }

    public async rename(source: Uri, target: Uri, options?: { overwrite?: boolean }): Promise<void> {
        await this.rpc.sendRequest('workspace.fs.rename', { source: source.toString(), target: target.toString(), options });
    }
}
