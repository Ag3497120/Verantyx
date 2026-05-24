import Foundation

class ChatViewModel: ObservableObject {
    @Published var messages: [String] = []

    func load() {
        messages = ["Hello from mobile!"]
    }
}
