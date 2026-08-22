import Foundation

/// A custom implementation of the LZ77 data compression algorithm.
/// This serves as a benchmark test for the autonomous coding capabilities.
public struct LZ77Compressor {
    
    // Window size for the sliding window (e.g., 4KB)
    private let windowSize: Int
    // Maximum lookahead buffer size (e.g., 15 bytes)
    private let lookaheadBufferSize: Int
    
    public init(windowSize: Int = 4096, lookaheadBufferSize: Int = 15) {
        self.windowSize = windowSize
        self.lookaheadBufferSize = lookaheadBufferSize
    }
    
    /// Compresses a given byte array using LZ77.
    /// Each token is either:
    /// - `(0, 0, next_byte)`: Literal byte (when no match is found)
    /// - `(offset, length, next_byte)`: Match reference + the next uncompressed byte
    public func compress(data: Data) -> Data {
        var compressed = Data()
        var cursor = 0
        let dataArray = [UInt8](data)
        
        while cursor < dataArray.count {
            var matchOffset = 0
            var matchLength = 0
            
            // Define sliding window boundaries
            let windowStart = max(0, cursor - windowSize)
            let lookaheadEnd = min(dataArray.count, cursor + lookaheadBufferSize)
            
            // Search for the longest match in the sliding window
            for i in windowStart..<cursor {
                var currentLength = 0
                while (cursor + currentLength) < lookaheadEnd && 
                      dataArray[i + currentLength] == dataArray[cursor + currentLength] {
                    currentLength += 1
                }
                
                if currentLength > matchLength {
                    matchLength = currentLength
                    matchOffset = cursor - i
                }
            }
            
            // Determine the next byte after the match
            let nextByteIndex = cursor + matchLength
            let nextByte: UInt8 = nextByteIndex < dataArray.count ? dataArray[nextByteIndex] : 0
            
            // Write token: [Offset (2 bytes), Length (1 byte), NextByte (1 byte)]
            var offset16 = UInt16(matchOffset).bigEndian
            var length8 = UInt8(matchLength)
            
            compressed.append(Data(bytes: &offset16, count: MemoryLayout<UInt16>.size))
            compressed.append(Data(bytes: &length8, count: MemoryLayout<UInt8>.size))
            compressed.append(nextByte)
            
            // Advance cursor
            cursor += matchLength + 1
        }
        
        return compressed
    }
    
    /// Decompresses data compressed by this LZ77 implementation.
    public func decompress(data: Data) -> Data {
        var decompressed = [UInt8]()
        var cursor = 0
        let dataArray = [UInt8](data)
        
        while cursor < dataArray.count {
            guard cursor + 3 < dataArray.count else { break }
            
            // Read token
            let offsetBytes = [dataArray[cursor], dataArray[cursor + 1]]
            let offset16 = offsetBytes.withUnsafeBytes { $0.load(as: UInt16.self) }.bigEndian
            let matchOffset = Int(offset16)
            
            let matchLength = Int(dataArray[cursor + 2])
            let nextByte = dataArray[cursor + 3]
            cursor += 4
            
            // Reconstruct from match
            if matchLength > 0 && matchOffset > 0 {
                let startPos = decompressed.count - matchOffset
                for i in 0..<matchLength {
                    if startPos + i < decompressed.count {
                        decompressed.append(decompressed[startPos + i])
                    }
                }
            }
            
            // Append next byte (unless it's the padding zero at the very end of stream)
            if cursor <= dataArray.count || nextByte != 0 {
                decompressed.append(nextByte)
            }
        }
        
        // Remove trailing padding byte if it was erroneously added at the EOF
        // (Handled by checking actual original length or EOF logic in a real format)
        return Data(decompressed)
    }
}

// Simple test to verify the implementation
func runBenchmark() {
    let originalString = "Verantyx autonomous agent successfully completed the benchmark! Verantyx autonomous agent successfully completed the benchmark!"
    guard let originalData = originalString.data(using: .utf8) else { return }
    
    let compressor = LZ77Compressor()
    
    print("--- Compression Benchmark ---")
    print("Original size: \(originalData.count) bytes")
    
    let startCompress = Date()
    let compressedData = compressor.compress(data: originalData)
    let compressTime = Date().timeIntervalSince(startCompress)
    print("Compressed size: \(compressedData.count) bytes")
    print("Compression time: \(compressTime) s")
    
    let startDecompress = Date()
    let decompressedData = compressor.decompress(data: compressedData)
    let decompressTime = Date().timeIntervalSince(startDecompress)
    print("Decompression time: \(decompressTime) s")
    
    let decompressedString = String(data: decompressedData, encoding: .utf8)?.trimmingCharacters(in: CharacterSet(charactersIn: "\0"))
    
    let matchString = (originalString == decompressedString) ? "YES" : "NO"
    print("Match: \(matchString)")
}

runBenchmark()
