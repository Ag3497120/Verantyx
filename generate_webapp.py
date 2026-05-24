import os

base_dir = "/Users/motonishikoudai/verantyx-cli/sample-polyglot-project"

files = {
    # FRONTEND (React + Vite)
    "frontend/package.json": """{
  "name": "poly-web",
  "private": true,
  "version": "0.0.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "lint": "eslint .",
    "preview": "vite preview"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "lucide-react": "^0.453.0"
  },
  "devDependencies": {
    "@types/react": "^18.3.3",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.1",
    "typescript": "^5.5.3",
    "vite": "^5.4.1"
  }
}
""",
    "frontend/vite.config.ts": """import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
})
""",
    "frontend/index.html": """<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Polyglot Web App</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
""",
    "frontend/tsconfig.json": """{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true
  },
  "include": ["src"]
}
""",
    "frontend/src/main.tsx": """import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.tsx'
import './index.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
""",
    "frontend/src/index.css": """body {
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  background-color: #f5f5f5;
  color: #333;
}
""",
    "frontend/src/App.tsx": """import React from 'react';
import { Dashboard } from './components/Dashboard';
import { Header } from './components/Header';
import { Footer } from './components/Footer';
import './App.css';

function App() {
  return (
    <div className="app-container">
      <Header />
      <main>
        <Dashboard />
      </main>
      <Footer />
    </div>
  );
}

export default App;
""",
    "frontend/src/App.css": """.app-container {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
}
main {
  flex: 1;
  padding: 2rem;
}
""",
    "frontend/src/components/Header.tsx": """import React from 'react';
import './Header.css';

export const Header = () => {
  return (
    <header className="header">
      <h1>Polyglot AI Dashboard</h1>
      <nav>
        <a href="#home">Home</a>
        <a href="#settings">Settings</a>
      </nav>
    </header>
  );
};
""",
    "frontend/src/components/Header.css": """.header {
  background-color: #1a1a1a;
  color: white;
  padding: 1rem 2rem;
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.header a {
  color: white;
  margin-left: 1rem;
  text-decoration: none;
}
""",
    "frontend/src/components/Footer.tsx": """import React from 'react';

export const Footer = () => {
  return (
    <footer style={{ padding: '1rem', textAlign: 'center', backgroundColor: '#e0e0e0' }}>
      <p>&copy; 2026 Verantyx Corp. All rights reserved.</p>
    </footer>
  );
};
""",
    "frontend/src/components/Dashboard.tsx": """import React, { useEffect, useState } from 'react';
import { StatCard } from './StatCard';
import './Dashboard.css';

export const Dashboard = () => {
  const [data, setData] = useState({ users: 0, revenue: 0, status: 'Loading...' });

  useEffect(() => {
    // Simulate API fetch
    setTimeout(() => {
      setData({ users: 1250, revenue: 45000, status: 'Online' });
    }, 500);
  }, []);

  return (
    <div className="dashboard">
      <h2>System Overview</h2>
      <div className="stats-grid">
        <StatCard title="Active Users" value={data.users} />
        <StatCard title="Revenue ($)" value={data.revenue} />
        <StatCard title="System Status" value={data.status} />
      </div>
    </div>
  );
};
""",
    "frontend/src/components/Dashboard.css": """.dashboard {
  max-width: 1200px;
  margin: 0 auto;
}
.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: 1.5rem;
  margin-top: 1.5rem;
}
""",
    "frontend/src/components/StatCard.tsx": """import React from 'react';
import './StatCard.css';

interface Props {
  title: string;
  value: string | number;
}

export const StatCard = ({ title, value }: Props) => {
  return (
    <div className="stat-card">
      <h3>{title}</h3>
      <p className="stat-value">{value}</p>
    </div>
  );
};
""",
    "frontend/src/components/StatCard.css": """.stat-card {
  background: white;
  padding: 1.5rem;
  border-radius: 8px;
  box-shadow: 0 2px 4px rgba(0,0,0,0.1);
  text-align: center;
}
.stat-value {
  font-size: 2rem;
  font-weight: bold;
  color: #0066cc;
  margin: 0.5rem 0 0;
}
""",
    "frontend/src/utils/api.ts": """export const fetchApi = async (endpoint: string) => {
  console.log(`Fetching from ${endpoint}`);
  return { success: true };
};
""",

    # BACKEND (Node.js Express BFF)
    "bff/package.json": """{
  "name": "bff-service",
  "version": "1.0.0",
  "main": "index.js",
  "dependencies": {
    "express": "^4.18.2"
  }
}
""",
    "bff/index.js": """const express = require('express');
const app = express();
const routes = require('./routes');

app.use('/api', routes);

app.listen(3000, () => {
  console.log('BFF Service running on port 3000');
});
""",
    "bff/routes.js": """const express = require('express');
const router = express.Router();
const controller = require('./controller');

router.get('/status', controller.getStatus);

module.exports = router;
""",
    "bff/controller.js": """exports.getStatus = (req, res) => {
  res.json({ service: 'BFF', status: 'OK' });
};
""",

    # CORE API (Rust)
    "core_api/Cargo.toml": """[package]
name = "core_api"
version = "0.1.0"
edition = "2021"

[dependencies]
""",
    "core_api/src/main.rs": """mod engine;
mod models;

fn main() {
    println!("Core API starting...");
    engine::run();
}
""",
    "core_api/src/engine.rs": """use crate::models::Task;

pub fn run() {
    let task = Task { id: 1, name: String::from("Init") };
    println!("Running task: {}", task.name);
}
""",
    "core_api/src/models.rs": """pub struct Task {
    pub id: i32,
    pub name: String,
}
""",

    # DATA PIPELINE (Python)
    "data_pipeline/requirements.txt": """pandas
""",
    "data_pipeline/main.py": """from aggregator import aggregate_data
import sys

def main():
    print("Starting data pipeline...")
    aggregate_data()

if __name__ == "__main__":
    main()
""",
    "data_pipeline/aggregator.py": """from transformer import transform

def aggregate_data():
    data = {"users": [1, 2, 3]}
    result = transform(data)
    print("Aggregated:", result)
""",
    "data_pipeline/transformer.py": """def transform(data):
    return {"count": len(data.get("users", []))}
""",

    # CONFIG (YAML)
    "config/deployment.yaml": """apiVersion: apps/v1
kind: Deployment
metadata:
  name: polyglot-app
spec:
  replicas: 3
  template:
    spec:
      containers:
      - name: frontend
        image: polyglot-frontend:latest
""",
    "config/settings.json": """{
  "environment": "production",
  "log_level": "info"
}
"""
}

# Create files
for path, content in files.items():
    full_path = os.path.join(base_dir, path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, "w", encoding="utf-8") as f:
        f.write(content)

print(f"Created {len(files)} files successfully in {base_dir}")
