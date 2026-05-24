import SwiftUI

struct ExoSetupSheet: View {
    @Binding var isPresented: Bool
    @StateObject private var wizard = ExoSetupWizard.shared
    @EnvironmentObject var app: AppState
    
    var body: some View {
        VStack(spacing: 20) {
            Image(systemName: "bolt.horizontal.circle.fill")
                .font(.system(size: 48))
                .foregroundStyle(Color(red: 0.4, green: 0.8, blue: 0.5))
                .padding(.top, 20)
            
            Text("Exo Cluster Setup")
                .font(.title2.bold())
            
            switch wizard.state {
            case .idle, .scanning:
                ProgressView("Scanning system paths...")
                    .padding()
            
            case .needsLLM:
                Text("Pre-requisite Missing")
                    .font(.headline)
                    .foregroundStyle(.red)
                
                Text("To showcase the power of distributed inference, you need a local LLM configured first (e.g., Ollama or MLX).")
                    .font(.subheadline)
                    .multilineTextAlignment(.center)
                    .foregroundStyle(.secondary)
                
                Button("Configure LLM Now") {
                    isPresented = false
                    // Ideally route to LLM settings here
                }
                .buttonStyle(.borderedProminent)
                
            case .needsUV:
                Text("Missing: uv")
                    .font(.headline)
                    .foregroundStyle(.orange)
                
                Text("Exo uses 'uv' (the extremely fast Python package manager). We need to install it.")
                    .font(.subheadline)
                    .multilineTextAlignment(.center)
                    .foregroundStyle(.secondary)
                
                Button("Install 'uv' (Opens Terminal)") {
                    wizard.installUV()
                }
                .buttonStyle(.borderedProminent)
                
                Button("Check Again") {
                    wizard.scan()
                }
                .buttonStyle(.bordered)
                
            case .needsExo:
                Text("Missing: exo")
                    .font(.headline)
                    .foregroundStyle(.orange)
                
                Text("We need to install the Exo distributed inference engine.")
                    .font(.subheadline)
                    .multilineTextAlignment(.center)
                    .foregroundStyle(.secondary)
                
                HStack(spacing: 16) {
                    Button("Install Global (uv tool)") {
                        wizard.installExoGlobal()
                    }
                    .buttonStyle(.borderedProminent)
                    
                    Button("Check Again") {
                        wizard.scan()
                    }
                    .buttonStyle(.bordered)
                }
                
            case .ready:
                Text("Everything is Ready!")
                    .font(.headline)
                    .foregroundStyle(.green)
                
                Text("You can now enable Master or Worker mode in the settings.")
                    .font(.subheadline)
                    .multilineTextAlignment(.center)
                    .foregroundStyle(.secondary)
                
                Button("Start Master Node") {
                    app.exoRole = .master
                    app.exoEnabled = true
                    ExoEngine.shared.start()
                    isPresented = false
                }
                .buttonStyle(.borderedProminent)
                .tint(Color.green)
                
                // Showcase Tutorial Button
                Button("Test Distributed Inference (Tutorial)") {
                    // Tutorial logic here
                    isPresented = false
                    // Start an inference directly to show the user
                }
                .buttonStyle(.bordered)
                .tint(Color.blue)
            }
            
            Spacer()
            
            HStack {
                Spacer()
                Button("Cancel") {
                    isPresented = false
                }
                .keyboardShortcut(.escape, modifiers: [])
            }
        }
        .padding()
        .frame(width: 450, height: 400)
        .background(Color(red: 0.1, green: 0.1, blue: 0.13))
        .onAppear {
            wizard.scan()
        }
    }
}
