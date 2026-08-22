use notify::{Watcher, RecursiveMode, EventKind, event::ModifyKind};
use serde::{Deserialize, Serialize};
use std::collections::HashSet;
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex};
use std::time::Duration;
use tokio::sync::mpsc;
use tracing::{info, warn, error};

#[derive(Serialize, Deserialize, Default, Clone)]
pub struct NightwatchQueue {
    pub pending_files: HashSet<String>,
}

impl NightwatchQueue {
    pub fn load_or_create(root: &Path) -> Self {
        let path = root.join(".ronin").join("nightwatch_queue.json");
        if let Ok(data) = std::fs::read_to_string(&path) {
            if let Ok(q) = serde_json::from_str(&data) {
                return q;
            }
        }
        Self::default()
    }

    pub fn save(&self, root: &Path) {
        let ronin_dir = root.join(".ronin");
        if !ronin_dir.exists() {
            let _ = std::fs::create_dir_all(&ronin_dir);
        }
        let path = ronin_dir.join("nightwatch_queue.json");
        if let Ok(json) = serde_json::to_string_pretty(self) {
            let _ = std::fs::write(&path, json);
        }
    }

    pub fn push(&mut self, file: String) {
        self.pending_files.insert(file);
    }
}

pub struct FileObserver {
    queue: Arc<Mutex<NightwatchQueue>>,
    root_dir: PathBuf,
}

impl FileObserver {
    pub fn new(root_dir: PathBuf) -> Self {
        let initial_q = NightwatchQueue::load_or_create(&root_dir);
        Self {
            queue: Arc::new(Mutex::new(initial_q)),
            root_dir,
        }
    }

    fn run_baseline_scan(root: &Path, queue: Arc<Mutex<NightwatchQueue>>) {
        let flag_path = root.join(".ronin").join(".baseline_scanned");
        if flag_path.exists() {
            return;
        }

        info!("[Nightwatch] First boot detected! Commencing massive baseline Space-Time Scan (TimeMachine Mode)...");
        
        let valid_extensions = vec!["rs", "ts", "js", "py", "go", "c", "cpp", "h", "md", "txt", "json", "toml", "yaml"];
        
        let mut add_count = 0;
        let walker = ignore::WalkBuilder::new(root).hidden(false).build();
        for result in walker {
            if let Ok(entry) = result {
                if entry.file_type().map_or(false, |ft| ft.is_file()) {
                    let path = entry.path();
                    if let Some(ext) = path.extension().and_then(|e| e.to_str()) {
                        if valid_extensions.contains(&ext) {
                            if let Some(path_str) = path.to_str() {
                                if !path_str.contains(".git") && !path_str.contains(".ronin") && !path_str.contains("target") && !path_str.contains("node_modules") {
                                    if let Ok(mut q) = queue.lock() {
                                        q.push(path_str.to_string());
                                        add_count += 1;
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
        
        info!("[Nightwatch] Baseline Scan complete! Found {} text codebase files for JCross compression queue.", add_count);
        
        if let Ok(q) = queue.lock() {
            q.save(root);
        }
        
        if std::fs::create_dir_all(root.join(".ronin")).is_ok() {
            let _ = std::fs::write(&flag_path, "baseline_scan_complete_v1");
        }
    }

    /// Spawns a background task that listens for file edits and adds them to the semantic queue.
    pub fn start_detached(self) {
        let (tx, mut rx) = mpsc::channel(100);
        let root = self.root_dir.clone();
        
        let watcher_queue = self.queue.clone();
        
        // Execute baseline scan before booting the active watcher
        Self::run_baseline_scan(&self.root_dir, self.queue.clone());
        
        // Blocking thread for notify (as notify is synchronous via callbacks)
        std::thread::spawn(move || {
            // Configure watcher
            let mut watcher = notify::recommended_watcher(move |res: notify::Result<notify::Event>| {
                match res {
                    Ok(event) => {
                        // Focus on data modifications
                        if let EventKind::Modify(ModifyKind::Data(_)) = event.kind {
                            for path in event.paths {
                                if let Some(path_str) = path.to_str() {
                                    // Ignore .git, .ronin, target directories
                                    if path_str.contains(".git") || path_str.contains(".ronin") || path_str.contains("target") {
                                        continue;
                                    }
                                    let _ = tx.blocking_send(path_str.to_string());
                                }
                            }
                        }
                    },
                    Err(e) => error!("Watch error: {}", e),
                }
            }).expect("Failed to initialize file watcher");

            let _ = watcher.watch(&root, RecursiveMode::Recursive);
            
            // Keep thread alive
            #[allow(clippy::empty_loop)]
            loop {
                std::thread::sleep(Duration::from_secs(60));
            }
        });

        // Async task to debounce and save queue
        let root_for_task = self.root_dir.clone();
        tokio::spawn(async move {
            let mut pending_saves = 0;
            loop {
                tokio::select! {
                    Some(changed_file) = rx.recv() => {
                        if let Ok(mut q) = watcher_queue.lock() {
                            if q.pending_files.insert(changed_file.clone()) {
                                pending_saves += 1;
                            }
                        }
                    }
                    _ = tokio::time::sleep(Duration::from_secs(5)) => {
                        if pending_saves > 0 {
                            if let Ok(q) = watcher_queue.lock() {
                                q.save(&root_for_task);
                            }
                            pending_saves = 0;
                        }
                    }
                }
            }
        });
        
        info!("[Nightwatch Protocol] Observer awakened. Watching for semantic diffs in {}", self.root_dir.display());
    }
}
