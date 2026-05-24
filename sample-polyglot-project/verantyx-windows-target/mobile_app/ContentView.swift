// File: ContentView.swift
// JCross IR — Do not decode IDs
_JCROSS_頂_1_ = {
  _JCROSS_型_2_ : _JCROSS_核_3_,
  _JCROSS_型_4_ : _JCROSS_核_5_,
};

import SwiftUI

struct ContentView: View {
    @StateObject private var viewModel = ChatViewModel()
    @State private var lang: String = "en"
    
    var body: some View {
        VStack {
            Picker("Language", selection: $lang) {
                Text("English").tag("en")
                Text("日本語").tag("ja")
            }
            .pickerStyle(SegmentedPickerStyle())
            .onChange(of: lang) { newVal in
                viewModel.language = newVal
            }
            
            List(viewModel.messages) { message in
                HStack {
                    Text(formatLocalTime(message.timestamp))
                    Text(message.text)
                }
            }
            
            HStack {
                TextField(viewModel.t("placeholder"), text: .constant(""))
                Button(viewModel.t("send")) {
                    viewModel.send("sample")
                }
            }
        }
    }
    
    func formatLocalTime(_ iso: String) -> String {
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy/MM/dd HH:mm"
        formatter.timeZone = TimeZone.current
        if let date = ISO8601DateFormatter().date(from: iso) {
            return formatter.string(from: date)
        }
        return iso
    }
}