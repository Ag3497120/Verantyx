import os

base_dir = "/Users/motonishikoudai/verantyx-cli/sample-polyglot-project"

files = {
    "backend/Cargo.toml": """[package]
name = "polychat-backend"
version = "0.1.0"
edition = "2021"

[dependencies]
tokio = { version = "1", features = ["full"] }
serde = { version = "1.0", features = ["derive"] }
""",
    "backend/src/main.rs": """mod server;
mod routes;
mod models;

#[tokio::main]
async fn main() {
    println!("Starting PolyChat Backend...");
    server::start().await;
}
""",
    "backend/src/server.rs": """pub async fn start() {
    println!("Server running on port 8080");
}
""",
    "backend/src/routes.rs": """pub fn setup_routes() {
    println!("Setting up routes: /api/chat");
}
""",
    "backend/src/models.rs": """use serde::{Serialize, Deserialize};

#[derive(Serialize, Deserialize, Debug)]
pub struct Message {
    pub id: String,
    pub user: String,
    pub content: String,
}
""",
    "frontend/package.json": """{
  "name": "polychat-frontend",
  "version": "1.0.0",
  "dependencies": {
    "react": "^18.0.0",
    "typescript": "^4.9.0"
  }
}
""",
    "frontend/src/index.tsx": """import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';

const container = document.getElementById('root');
if (container) {
    const root = createRoot(container);
    root.render(<App />);
}
""",
    "frontend/src/App.tsx": """import React from 'react';
import { ChatBox } from './components/ChatBox';

export default function App() {
    return (
        <div className="app">
            <h1>PolyChat</h1>
            <ChatBox />
        </div>
    );
}
""",
    "frontend/src/components/ChatBox.tsx": """import React, { useState } from 'react';

export const ChatBox = () => {
    const [msg, setMsg] = useState("");

    const send = () => {
        console.log("Sending: ", msg);
        setMsg("");
    };

    return (
        <div>
            <input value={msg} onChange={e => setMsg(e.target.value)} />
            <button onClick={send}>Send</button>
        </div>
    );
};
""",
    "frontend/src/components/UserList.tsx": """import React from 'react';

export const UserList = () => {
    return <ul><li>User 1</li><li>User 2</li></ul>;
};
""",
    "frontend/src/api.ts": """export async function fetchMessages() {
    return [{ id: '1', user: 'system', content: 'Welcome to PolyChat' }];
}
""",
    "data_pipeline/requirements.txt": """pandas==2.0.0
numpy==1.24.0
""",
    "data_pipeline/main.py": """from processor import process_data

if __name__ == "__main__":
    print("Starting data pipeline...")
    process_data()
""",
    "data_pipeline/processor.py": """def process_data():
    print("Processing chat logs...")
""",
    "data_pipeline/analyzer.py": """def analyze_sentiment(text: str):
    return "Positive" if "good" in text else "Neutral"
""",
    "mobile_app/App.swift": """import SwiftUI

@main
struct PolyChatApp: App {
    var body: some Scene {
        WindowGroup {
            ContentView()
        }
    }
}
""",
    "mobile_app/ContentView.swift": """import SwiftUI

struct ContentView: View {
    var body: some View {
        VStack {
            Text("PolyChat Mobile")
                .font(.largeTitle)
        }
    }
}
""",
    "mobile_app/ChatViewModel.swift": """import Foundation

class ChatViewModel: ObservableObject {
    @Published var messages: [String] = []

    func load() {
        messages = ["Hello from mobile!"]
    }
}
""",
    "mobile_app/Network.swift": """import Foundation

class NetworkManager {
    static let shared = NetworkManager()
    func fetch() {
        print("Fetching data from backend")
    }
}
""",
    "config/settings.json": """{
  "api_endpoint": "http://localhost:8080",
  "enable_analytics": true,
  "max_users": 100
}
"""
}

for path, content in files.items():
    full_path = os.path.join(base_dir, path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, "w", encoding="utf-8") as f:
        f.write(content)

print("Created 20 files successfully in " + base_dir)
