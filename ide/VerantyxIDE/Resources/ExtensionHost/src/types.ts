import { URI } from 'vscode-uri';

export class Disposable {
    static from(...disposables: { dispose(): any }[]): Disposable {
        return new Disposable(() => {
            for (const d of disposables) {
                if (d && typeof d.dispose === 'function') {
                    d.dispose();
                }
            }
        });
    }

    private callOnDispose?: () => any;

    constructor(callOnDispose: () => any) {
        this.callOnDispose = callOnDispose;
    }

    dispose() {
        if (this.callOnDispose) {
            this.callOnDispose();
            this.callOnDispose = undefined;
        }
    }
}

export class Position {
    public readonly line: number;
    public readonly character: number;

    constructor(line: number, character: number) {
        this.line = line;
        this.character = character;
    }

    isBefore(other: Position): boolean {
        if (this.line < other.line) return true;
        if (this.line === other.line) return this.character < other.character;
        return false;
    }
    
    // ... other standard methods like isAfter, isEqual, translate, with
}

export class Range {
    public readonly start: Position;
    public readonly end: Position;

    constructor(startLine: number, startCharacter: number, endLine: number, endCharacter: number);
    constructor(start: Position, end: Position);
    constructor(startLineOrStart: any, startCharacterOrEnd: any, endLine?: number, endCharacter?: number) {
        if (typeof startLineOrStart === 'number') {
            this.start = new Position(startLineOrStart, startCharacterOrEnd);
            this.end = new Position(endLine as number, endCharacter as number);
        } else {
            this.start = startLineOrStart;
            this.end = startCharacterOrEnd;
        }
    }
}

export class Location {
    public uri: URI;
    public range: Range;

    constructor(uri: URI, rangeOrPosition: Range | Position) {
        this.uri = uri;
        if (rangeOrPosition instanceof Position) {
            this.range = new Range(rangeOrPosition, rangeOrPosition);
        } else {
            this.range = rangeOrPosition;
        }
    }
}

export { URI as Uri };
