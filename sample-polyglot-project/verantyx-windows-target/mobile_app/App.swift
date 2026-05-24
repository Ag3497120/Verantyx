// File: App.swift
// JCross IR — Do not decode IDs
_JCROSS_頂_1_ = {
  _JCROSS_型_2_ : _JCROSS_核_3_,
  _JCROSS_型_4_ : _JCROSS_核_5_,
};

import SwiftUI
import Foundation

// All time converted to UTC at entry points
extension Date {
    var utcISO: String {
        let formatter = ISO8601DateFormatter()
        formatter.timeZone = TimeZone(secondsFromGMT: 0)
        return formatter.string(from: self)
    }
}

@main
struct PolyChatApp: App {
    var body: some Scene {
        WindowGroup {
            ContentView()
        }
    }
}