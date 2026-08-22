export declare class RPCClient {
    private requestIDCounter;
    private pendingRequests;
    constructor();
    private handleMessage;
    private handleRequestFromSwift;
    sendNotification(method: string, params?: any): void;
    sendRequest(method: string, params?: any): Promise<any>;
    private sendResponse;
}
//# sourceMappingURL=rpc.d.ts.map