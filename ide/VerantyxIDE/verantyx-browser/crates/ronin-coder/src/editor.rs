use std::path::{Path, PathBuf};
use std::fs;
use crate::protocol::{ReplaceRequest, EditResult};

pub struct FileEditor {
    root: PathBuf,
}

impl FileEditor {
    pub fn new(root: impl AsRef<Path>) -> Self {
        Self {
            root: root.as_ref().to_path_buf(),
        }
    }

    pub fn apply(&self, req: &ReplaceRequest) -> EditResult {
        let path = self.root.join(&req.path);
        
        if !path.exists() {
            // Check if it's an intended file creation? 
            // In Aider, if content is empty and file doesn't exist, we create it.
            // For now, let's allow file creation if search is empty.
            if req.search.trim().is_empty() {
                if let Some(parent) = path.parent() {
                    let _ = fs::create_dir_all(parent);
                }
                match fs::write(&path, &req.replace) {
                    Ok(_) => return EditResult::ok(&req.path, "File created successfully."),
                    Err(e) => return EditResult::err(&req.path, format!("Failed to create file: {}", e)),
                }
            } else {
                return EditResult::err(&req.path, "File does not exist and search block is not empty.");
            }
        }

        let content = match fs::read_to_string(&path) {
            Ok(c) => c,
            Err(e) => return EditResult::err(&req.path, format!("Failed to read file: {}", e)),
        };

        // 1. Precise exact match
        let count = content.matches(&req.search).count();
        if count == 1 {
            let replaced = content.replace(&req.search, &req.replace);
            return self.write_and_return(&path, &req.path, &replaced);
        }

        if count > 1 {
            return EditResult::err(
                &req.path,
                format!("Search block matched {} times. Must be uniquely identifiable. Add more context to your search block.", count)
            );
        }

        // 2. Whitespace agnostic fuzzy match fallback (Simulated)
        // Just normalize `\r\n` to `\n` and double spaces to single spaces as a first pass
        let norm_content = content.replace("\r\n", "\n");
        let norm_search = req.search.replace("\r\n", "\n");
        
        let count = norm_content.matches(&norm_search).count();
        if count == 1 {
            let replaced = norm_content.replace(&norm_search, &req.replace);
            return self.write_and_return(&path, &req.path, &replaced);
        }

        EditResult::err(
            &req.path,
            "Search block not found exactly in the file. Context mismatch. Please ensure you quote the original code exactly, including leading spaces."
        )
    }

    fn write_and_return(&self, abs_path: &Path, rel_path: &str, content: &str) -> EditResult {
        match fs::write(abs_path, content) {
            Ok(_) => EditResult::ok(rel_path, "Replaced successfully."),
            Err(e) => EditResult::err(rel_path, format!("Failed to write updated file: {}", e)),
        }
    }
}
