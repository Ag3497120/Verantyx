// File: ChatViewModel.swift
// JCross IR — Do not decode IDs
_JCROSS_頂_1_ = {
  _JCROSS_型_2_ : _JCROSS_核_3_,
  _JCROSS_型_4_ : _JCROSS_核_5_,
  _JCROSS_型_6_ : _JCROSS_核_7_,
};

import Foundation

class ChatViewModel: ObservableObject {
    @Published var messages: [Message] = []
    @Published var language: String = "en"
    
    let i18n: [String: [String: String]] = [
        "en": ["send": "Send", "placeholder": "Type a message..."],
        "ja": ["send": "送信", "placeholder": "メッセージを入力..."]
    ]
    
    func t(_ key: String) -> String {
        return i18n[language]?[key] ?? key
    }
    
    func load() {
        // existing load logic, timestamps always UTC ISO
    }
    
    func send(_ text: String) {
        let utcISO = Date().utcISO
        // send with UTC timestamp
    }
}