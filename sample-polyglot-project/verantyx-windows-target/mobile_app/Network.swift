// File: Network.swift
// JCross IR — Do not decode IDs
_JCROSS_頂_1_ = {
  _JCROSS_型_2_ : _JCROSS_核_3_,
  _JCROSS_型_4_ : _JCROSS_核_5_,
};

import Foundation

class NetworkManager {
    func fetch(completion: @escaping ([Message]) -> Void) {
        // All timestamps treated as UTC
        let url = URL(string: "https://api.example.com/messages")!
        URLSession.shared.dataTask(with: url) { data, _, _ in
            if let data = data, let messages = try? JSONDecoder().decode([Message].self, from: data) {
                DispatchQueue.main.async {
                    completion(messages)
                }
            }
        }.resume()
    }
}