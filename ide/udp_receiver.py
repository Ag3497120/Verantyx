import socket
import struct
import sys

def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", 9999))
    print("Listening on UDP port 9999...")

    frames = {}
    last_played_frame = 0

    with open("/Users/motonishikoudai/verantyx-cli/cli/stream.h264", "wb") as f:
        while True:
            data, addr = sock.recvfrom(2048)
            if len(data) < 12:
                continue
            
            frame_seq, frag_idx, total_frags, payload_size = struct.unpack("<IHHI", data[:12])
            
            payload = data[12:12+payload_size]
            
            if frame_seq < last_played_frame:
                continue
                
            if frame_seq not in frames:
                frames[frame_seq] = { "total": total_frags, "fragments": {}, "received": 0 }
                
            if frag_idx not in frames[frame_seq]["fragments"]:
                frames[frame_seq]["fragments"][frag_idx] = payload
                frames[frame_seq]["received"] += 1
            
            if frames[frame_seq]["received"] == total_frags:
                # Frame complete!
                frame_data = b"".join(frames[frame_seq]["fragments"][i] for i in range(total_frags))
                f.write(frame_data)
                f.flush()
                print(f"Saved complete frame {frame_seq}, {total_frags} frags, size: {len(frame_data)} bytes")
                last_played_frame = frame_seq
                
                # Cleanup old frames
                keys = list(frames.keys())
                for k in keys:
                    if k <= frame_seq:
                        del frames[k]

if __name__ == "__main__":
    main()
