import SwiftUI
import AVFoundation

class SpinnerNSView: NSView {
    var playerLayer: AVPlayerLayer?

    override func layout() {
        super.layout()
        playerLayer?.frame = self.bounds
        self.layer?.cornerRadius = min(self.bounds.width, self.bounds.height) / 2
    }
}

struct VideoSpinnerView: NSViewRepresentable {
    
    let videoURL: URL
    let speed: Float
    
    func makeNSView(context: Context) -> NSView {
        let view = SpinnerNSView()
        view.wantsLayer = true
        
        let playerItem = AVPlayerItem(url: videoURL)
        let player = AVPlayer(playerItem: playerItem)
        let playerLayer = AVPlayerLayer(player: player)
        
        // 動画の青い部分を切り出すために resizeAspectFill を使用
        playerLayer.videoGravity = .resizeAspectFill
        view.layer?.addSublayer(playerLayer)
        view.playerLayer = playerLayer
        
        // 丸く切り抜く
        view.layer?.masksToBounds = true
        
        context.coordinator.player = player
        context.coordinator.playerLayer = playerLayer
        
        // ループの終端で停止しないようにする
        player.actionAtItemEnd = .none
        
        // 時間を監視してピンポンループ（順再生・逆再生）を実現
        context.coordinator.timeObserver = player.addPeriodicTimeObserver(forInterval: CMTime(value: 1, timescale: 30), queue: .main) { [weak player] time in
            guard let player = player, let duration = player.currentItem?.duration.seconds, duration > 0 else { return }
            let current = time.seconds
            
            // 順再生の終わり
            if player.rate > 0 && current >= duration - 0.1 {
                player.rate = -speed
            } 
            // 逆再生の始まり
            else if player.rate < 0 && current <= 0.1 {
                player.rate = speed
            } 
            // 停止している場合は再生開始
            else if player.rate == 0 {
                player.rate = speed
            }
        }
        
        player.rate = speed
        player.play()
        
        return view
    }
    
    func updateNSView(_ nsView: NSView, context: Context) {
        // レイヤーサイズは SpinnerNSView の layout() で更新されます
    }
    
    func makeCoordinator() -> Coordinator {
        Coordinator()
    }
    
    class Coordinator {
        var player: AVPlayer?
        var playerLayer: AVPlayerLayer?
        var timeObserver: Any?
        
        deinit {
            if let timeObserver = timeObserver {
                player?.removeTimeObserver(timeObserver)
            }
        }
    }
}
