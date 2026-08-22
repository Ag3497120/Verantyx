import Foundation

@MainActor
final class WorkspaceFileSystem {
    static let shared = WorkspaceFileSystem()
    private let fileManager = FileManager.default

    private init() {}

    func stat(uri: String) throws -> [String: Any] {
        guard let url = URL(string: uri) else { throw NSError(domain: "FS", code: 1, userInfo: nil) }
        let attrs = try fileManager.attributesOfItem(atPath: url.path)
        
        let type: Int
        if let fileType = attrs[.type] as? FileAttributeType {
            type = (fileType == .typeDirectory) ? 2 : 1
        } else {
            type = 0 // Unknown
        }
        
        return [
            "type": type,
            "ctime": (attrs[.creationDate] as? Date)?.timeIntervalSince1970 ?? 0,
            "mtime": (attrs[.modificationDate] as? Date)?.timeIntervalSince1970 ?? 0,
            "size": attrs[.size] as? Int ?? 0
        ]
    }

    func readDirectory(uri: String) throws -> [[Any]] {
        guard let url = URL(string: uri) else { throw NSError(domain: "FS", code: 1, userInfo: nil) }
        let contents = try fileManager.contentsOfDirectory(atPath: url.path)
        
        return contents.compactMap { name -> [Any]? in
            let childPath = url.appendingPathComponent(name).path
            var isDir: ObjCBool = false
            if fileManager.fileExists(atPath: childPath, isDirectory: &isDir) {
                let type = isDir.boolValue ? 2 : 1
                return [name, type]
            }
            return nil
        }
    }

    func readFile(uri: String) throws -> String {
        guard let url = URL(string: uri) else { throw NSError(domain: "FS", code: 1, userInfo: nil) }
        let data = try Data(contentsOf: url)
        return data.base64EncodedString()
    }

    func writeFile(uri: String, contentBase64: String) throws {
        guard let url = URL(string: uri), let data = Data(base64Encoded: contentBase64) else { 
            throw NSError(domain: "FS", code: 1, userInfo: nil) 
        }
        try data.write(to: url, options: .atomic)
    }

    func createDirectory(uri: String) throws {
        guard let url = URL(string: uri) else { throw NSError(domain: "FS", code: 1, userInfo: nil) }
        try fileManager.createDirectory(at: url, withIntermediateDirectories: true)
    }

    func delete(uri: String) throws {
        guard let url = URL(string: uri) else { throw NSError(domain: "FS", code: 1, userInfo: nil) }
        try fileManager.removeItem(at: url)
    }

    func rename(source: String, target: String) throws {
        guard let srcURL = URL(string: source), let tgtURL = URL(string: target) else { 
            throw NSError(domain: "FS", code: 1, userInfo: nil) 
        }
        try fileManager.moveItem(at: srcURL, to: tgtURL)
    }
}
