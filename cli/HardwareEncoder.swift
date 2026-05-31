import Foundation
import VideoToolbox
import CoreMedia
import Network

// MARK: - IPC and UDP Structures

struct SharedFrame {
    var sequenceNumber: UInt32
    var width: UInt32
    var height: UInt32
    var format: UInt32
}

struct UDPHeader {
    var frameSequence: UInt32
    var fragmentIndex: UInt16
    var totalFragments: UInt16
    var payloadSize: UInt32
}

// MARK: - Setup Network

var targetIP = "127.0.0.1"
if CommandLine.arguments.count > 1 {
    targetIP = CommandLine.arguments[1]
}
print("Target UDP IP: \(targetIP)")

var sock = socket(AF_INET, SOCK_DGRAM, 0)
if sock < 0 {
    print("Failed to create UDP socket")
    exit(1)
}
var targetAddr = sockaddr_in()
targetAddr.sin_len = UInt8(MemoryLayout<sockaddr_in>.size)
targetAddr.sin_family = sa_family_t(AF_INET)
targetAddr.sin_port = in_port_t(9999).bigEndian
targetAddr.sin_addr.s_addr = inet_addr(targetIP)

// MARK: - VideoToolbox Callback

func processSampleBuffer(sampleBuffer: CMSampleBuffer, isKeyFrame: Bool, frameSequence: UInt32) {
    guard let dataBuffer = CMSampleBufferGetDataBuffer(sampleBuffer) else { return }
    var length = 0
    var dataPointer: UnsafeMutablePointer<Int8>? = nil
    CMBlockBufferGetDataPointer(dataBuffer, atOffset: 0, lengthAtOffsetOut: nil, totalLengthOut: &length, dataPointerOut: &dataPointer)
    
    guard let data = dataPointer else { return }
    
    var frameData = Data()
    
    // 1. Extract SPS and PPS for Keyframes
    if isKeyFrame {
        if let formatDesc = CMSampleBufferGetFormatDescription(sampleBuffer) {
            var spsSize: Int = 0
            var spsCount: Int = 0
            var spsPtr: UnsafePointer<UInt8>? = nil
            CMVideoFormatDescriptionGetH264ParameterSetAtIndex(formatDesc, parameterSetIndex: 0, parameterSetPointerOut: &spsPtr, parameterSetSizeOut: &spsSize, parameterSetCountOut: &spsCount, nalUnitHeaderLengthOut: nil)
            
            var ppsSize: Int = 0
            var ppsCount: Int = 0
            var ppsPtr: UnsafePointer<UInt8>? = nil
            CMVideoFormatDescriptionGetH264ParameterSetAtIndex(formatDesc, parameterSetIndex: 1, parameterSetPointerOut: &ppsPtr, parameterSetSizeOut: &ppsSize, parameterSetCountOut: &ppsCount, nalUnitHeaderLengthOut: nil)
            
            let startCode: [UInt8] = [0, 0, 0, 1]
            if let sps = spsPtr {
                frameData.append(contentsOf: startCode)
                frameData.append(sps, count: spsSize)
            }
            if let pps = ppsPtr {
                frameData.append(contentsOf: startCode)
                frameData.append(pps, count: ppsSize)
            }
        }
    }
    
    // 2. AVCC to Annex-B Conversion
    var offset = 0
    while offset < length - 4 {
        var nalLength: UInt32 = 0
        memcpy(&nalLength, data + offset, 4)
        nalLength = UInt32(bigEndian: nalLength)
        
        let startCode: [UInt8] = [0, 0, 0, 1]
        frameData.append(contentsOf: startCode)
        frameData.append(data.advanced(by: offset + 4).withMemoryRebound(to: UInt8.self, capacity: Int(nalLength)) { $0 }, count: Int(nalLength))
        
        offset += 4 + Int(nalLength)
    }
    
    // 3. UDP Fragmentation and Transmission
    let mtu = 1400
    let totalBytes = frameData.count
    let numFragments = (totalBytes + mtu - 1) / mtu
    
    frameData.withUnsafeBytes { rawBuffer in
        guard let baseAddress = rawBuffer.bindMemory(to: UInt8.self).baseAddress else { return }
        
        for i in 0..<numFragments {
            let chunkOffset = i * mtu
            let fragSize = min(mtu, totalBytes - chunkOffset)
            
            var header = UDPHeader(
                frameSequence: frameSequence.littleEndian,
                fragmentIndex: UInt16(i).littleEndian,
                totalFragments: UInt16(numFragments).littleEndian,
                payloadSize: UInt32(fragSize).littleEndian
            )
            
            var packet = Data()
            withUnsafeBytes(of: &header) { pktHeader in
                packet.append(contentsOf: pktHeader)
            }
            packet.append(baseAddress + chunkOffset, count: fragSize)
            
            packet.withUnsafeBytes { pktData in
                let _ = withUnsafePointer(to: &targetAddr) { sa in
                    sa.withMemoryRebound(to: sockaddr.self, capacity: 1) { saPtr in
                        sendto(sock, pktData.baseAddress!, packet.count, 0, saPtr, socklen_t(MemoryLayout<sockaddr_in>.size))
                    }
                }
            }
            print("Sent UDP packet for frame \(frameSequence) frag \(i)/\(numFragments) payload: \(fragSize)")
            fflush(stdout)
        }
    }
}

// MARK: - VideoToolbox Setup

var compressionSession: VTCompressionSession?
var isEncoding = true
var totalBytesEncoded = 0

func setupEncoder(width: Int32, height: Int32) {
    let status = VTCompressionSessionCreate(allocator: kCFAllocatorDefault,
                                            width: width,
                                            height: height,
                                            codecType: kCMVideoCodecType_H264,
                                            encoderSpecification: nil,
                                            imageBufferAttributes: nil,
                                            compressedDataAllocator: nil,
                                            outputCallback: { (outputCallbackRefCon, sourceFrameRefCon, status, infoFlags, sampleBuffer) in
        print("VideoToolbox Callback FIRED! Status: \(status)")
        fflush(stdout)
        if status != noErr {
            print("Encoding error: \(status)")
            return
        }
        guard let sampleBuffer = sampleBuffer else { return }
        let isKeyFrame = !infoFlags.contains(.frameDropped) && (CMSampleBufferGetSampleAttachmentsArray(sampleBuffer, createIfNecessary: false) as? [[CFString: Any]] == nil || (CMSampleBufferGetSampleAttachmentsArray(sampleBuffer, createIfNecessary: false) as? [[CFString: Any]])?.first?[kCMSampleAttachmentKey_NotSync] == nil)
        
        let frameSequence = sourceFrameRefCon!.assumingMemoryBound(to: UInt32.self).pointee
        
        processSampleBuffer(sampleBuffer: sampleBuffer, isKeyFrame: isKeyFrame, frameSequence: frameSequence)
        
    },
                                            refcon: nil,
                                            compressionSessionOut: &compressionSession)
    
    if status != noErr {
        print("Failed to create VTCompressionSession")
        exit(1)
    }
    
    VTSessionSetProperty(compressionSession!, key: kVTCompressionPropertyKey_RealTime, value: kCFBooleanTrue)
    VTSessionSetProperty(compressionSession!, key: kVTCompressionPropertyKey_ProfileLevel, value: kVTProfileLevel_H264_High_AutoLevel)
    VTCompressionSessionPrepareToEncodeFrames(compressionSession!)
}

// MARK: - Main IPC Loop

let filePath = NSHomeDirectory() + "/Verantyx_VR_Drive/SteamVR_Prefix/drive_c/vr_shared_frame.dat"
let mapSize = 16 + 1920 * 1080 * 4 + 130 // Added 130 bytes for Hand Tracking

print("Waiting for vr_shared_frame.dat...")
while true {
    if FileManager.default.fileExists(atPath: filePath) {
        do {
            let attr = try FileManager.default.attributesOfItem(atPath: filePath)
            if let fileSize = attr[FileAttributeKey.size] as? UInt64 {
                if fileSize >= mapSize {
                    break
                }
            }
        } catch {}
    }
    Thread.sleep(forTimeInterval: 0.5)
}

let fd = open(filePath, O_RDONLY)
if fd < 0 {
    print("Failed to open file")
    exit(1)
}

let mapPtr = mmap(nil, mapSize, PROT_READ, MAP_SHARED, fd, 0)
if mapPtr == MAP_FAILED {
    print("mmap failed")
    exit(1)
}

let headerPtr = mapPtr!.bindMemory(to: SharedFrame.self, capacity: 1)
let pixelPtr = mapPtr! + MemoryLayout<SharedFrame>.size
let handsMapPtr = mapPtr! + 16 + 1920 * 1080 * 4

var lastSeq: UInt32 = 0
var pixelBuffer: CVPixelBuffer?
var framesEncoded = 0
var currentFrameSequence: UInt32 = 0
var currentWidth = 0
var currentHeight = 0

// MARK: - Hand Tracking UDP Server
let listener = try? NWListener(using: .udp, on: 9998)
listener?.newConnectionHandler = { connection in
    connection.start(queue: .global())
    func receiveNext() {
        connection.receiveMessage { data, context, isComplete, error in
            if let data = data, data.count == 130 {
                data.withUnsafeBytes { rawBuffer in
                    memcpy(handsMapPtr, rawBuffer.baseAddress, 130)
                }
            }
            if error == nil {
                receiveNext()
            }
        }
    }
    receiveNext()
}
listener?.start(queue: .global())
print("Listening for Hand Tracking on UDP 9998...")

print("Starting native read loop and UDP transmission on port 9999...")

while isEncoding {
    let currentSeq = headerPtr.pointee.sequenceNumber
    if currentSeq != lastSeq && currentSeq > 0 {
        let width = Int(headerPtr.pointee.width)
        let height = Int(headerPtr.pointee.height)
        
        if width != currentWidth || height != currentHeight {
            if compressionSession != nil {
                VTCompressionSessionInvalidate(compressionSession!)
                compressionSession = nil
            }
            pixelBuffer = nil
            currentWidth = width
            currentHeight = height
            print("Resolution changed to \(width)x\(height)")
        }
        
        if compressionSession == nil && width > 0 && height > 0 {
            print("Initializing VideoToolbox encoder for \(width)x\(height)...")
            fflush(stdout)
            setupEncoder(width: Int32(width), height: Int32(height))
        }
        
        if width > 0 && height > 0 {
            if pixelBuffer == nil {
                CVPixelBufferCreate(kCFAllocatorDefault, width, height, kCVPixelFormatType_32BGRA, nil, &pixelBuffer)
            }
            
            if let pb = pixelBuffer {
                CVPixelBufferLockBaseAddress(pb, [])
                let dst = CVPixelBufferGetBaseAddress(pb)!
                let bytesPerRow = CVPixelBufferGetBytesPerRow(pb)
                
                if bytesPerRow == width * 4 {
                    memcpy(dst, pixelPtr, width * height * 4)
                } else {
                    for y in 0..<height {
                        memcpy(dst + y * bytesPerRow, pixelPtr + y * width * 4, width * 4)
                    }
                }
                
                CVPixelBufferUnlockBaseAddress(pb, [])
                
                let presentationTime = CMTime(value: CMTimeValue(framesEncoded), timescale: 90)
                currentFrameSequence = currentSeq
                
                var refConVal = currentSeq
                
                let status = VTCompressionSessionEncodeFrame(compressionSession!,
                                                             imageBuffer: pb,
                                                             presentationTimeStamp: presentationTime,
                                                             duration: CMTime.invalid,
                                                             frameProperties: nil,
                                                             sourceFrameRefcon: &refConVal,
                                                             infoFlagsOut: nil)
                if status == noErr {
                    framesEncoded += 1
                } else {
                    print("VTCompressionSessionEncodeFrame failed with status: \(status)")
                    fflush(stdout)
                }
            }
        }
        lastSeq = currentSeq
    }
    
    usleep(1000)
}
