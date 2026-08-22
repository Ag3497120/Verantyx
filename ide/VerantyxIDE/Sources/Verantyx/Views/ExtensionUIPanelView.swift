import SwiftUI

struct ExtensionUIPanelView: View {
    @ObservedObject var uiManager = ExtensionUIManager.shared

    var body: some View {
        Group {
            if uiManager.isPromptPresented {
                ZStack {
                    // Dimmed background
                    Color.black.opacity(0.4)
                        .edgesIgnoringSafeArea(.all)
                        .onTapGesture {
                            uiManager.cancelPrompt()
                        }
                    
                    VStack {
                        switch uiManager.currentPrompt {
                        case .quickPick(_, _):
                            quickPickView
                        case .inputBox(_):
                            inputBoxView
                        case .none:
                            EmptyView()
                        }
                    }
                    .frame(width: 500)
                    .background(Color(NSColor.windowBackgroundColor))
                    .cornerRadius(10)
                    .shadow(radius: 20)
                    .padding(.top, 100)
                }
            }
        }
    }

    private var quickPickView: some View {
        VStack(spacing: 0) {
            TextField("Search...", text: $uiManager.quickPickSearchText)
                .textFieldStyle(RoundedBorderTextFieldStyle())
                .padding()
                .onChange(of: uiManager.quickPickSearchText) { _, newValue in
                    if newValue.isEmpty {
                        uiManager.quickPickFilteredItems = uiManager.quickPickItems
                    } else {
                        uiManager.quickPickFilteredItems = uiManager.quickPickItems.filter { $0.localizedCaseInsensitiveContains(newValue) }
                    }
                }
            
            List(uiManager.quickPickFilteredItems, id: \.self) { item in
                Button(action: {
                    uiManager.submitPrompt(value: item)
                }) {
                    Text(item)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(.vertical, 4)
                }
                .buttonStyle(PlainButtonStyle())
            }
            .frame(maxHeight: 300)
        }
    }

    private var inputBoxView: some View {
        VStack(spacing: 12) {
            Text(uiManager.inputBoxPrompt)
                .font(.headline)
            
            TextField("", text: $uiManager.inputBoxText)
                .textFieldStyle(RoundedBorderTextFieldStyle())
                .onSubmit {
                    uiManager.submitPrompt(value: uiManager.inputBoxText)
                }
            
            HStack {
                Spacer()
                Button("Cancel") {
                    uiManager.cancelPrompt()
                }
                .keyboardShortcut(.escape, modifiers: [])
                
                Button("OK") {
                    uiManager.submitPrompt(value: uiManager.inputBoxText)
                }
                .keyboardShortcut(.defaultAction)
            }
        }
        .padding()
    }
}
