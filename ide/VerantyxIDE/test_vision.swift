import Foundation
import Vision
import AppKit

func computeSimilarity(base64A: String, base64B: String) throws -> Float {
    guard let dataA = Data(base64Encoded: base64A),
          let dataB = Data(base64Encoded: base64B),
          let imgA = NSImage(data: dataA)?.cgImage(forProposedRect: nil, context: nil, hints: nil),
          let imgB = NSImage(data: dataB)?.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
        return 0.0
    }
    
    let requestA = VNGenerateImageFeaturePrintRequest()
    let requestB = VNGenerateImageFeaturePrintRequest()
    
    let handlerA = VNImageRequestHandler(cgImage: imgA, options: [:])
    let handlerB = VNImageRequestHandler(cgImage: imgB, options: [:])
    
    try handlerA.perform([requestA])
    try handlerB.perform([requestB])
    
    guard let obsA = requestA.results?.first as? VNFeaturePrintObservation,
          let obsB = requestB.results?.first as? VNFeaturePrintObservation else {
        return 0.0
    }
    
    var distance: Float = 0
    try obsA.computeDistance(&distance, to: obsB)
    return distance
}

print("compiled")
