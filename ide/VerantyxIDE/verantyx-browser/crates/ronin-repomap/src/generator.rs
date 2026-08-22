use ignore::WalkBuilder;
use std::collections::BTreeMap;
use std::ffi::OsStr;
use std::fs;
use std::path::{Path, PathBuf};
use tracing::debug;
use tree_sitter::{Parser, Query, QueryCursor, StreamingIterator};

pub struct RepoMap {
    pub files: BTreeMap<String, Vec<String>>,
}

impl RepoMap {
    pub fn render(&self) -> String {
        let mut out = String::from("Repository Abstract Syntax Map (Aider Style):\n\n");
        for (file, tags) in &self.files {
            out.push_str(&format!("{}:\n", file));
            if tags.is_empty() {
                out.push_str("  (no exported structural symbols found)\n");
            } else {
                for tag in tags {
                    out.push_str(&format!("  {}\n", tag));
                }
            }
        }
        out
    }
}

pub struct RepoMapGenerator {
    root: PathBuf,
}

impl RepoMapGenerator {
    pub fn new(root: impl AsRef<Path>) -> Self {
        Self {
            root: root.as_ref().to_path_buf(),
        }
    }

    pub fn generate(&self) -> anyhow::Result<RepoMap> {
        debug!("[RepoMap] Starting AST traversal from {}", self.root.display());
        let mut map = RepoMap { files: BTreeMap::new() };

        let walker = WalkBuilder::new(&self.root)
            .hidden(true)
            .git_ignore(true)
            .build();

        let mut parser = Parser::new();
        let language = tree_sitter_rust::LANGUAGE.into();
        parser.set_language(&language).expect("Error loading Rust grammar");

        let query = Query::new(&language, r#"
            (struct_item name: (type_identifier) @name) @struct
            (enum_item name: (type_identifier) @name) @enum
            (trait_item name: (type_identifier) @name) @trait
            (impl_item type: (type_identifier) @name) @impl
            (function_item name: (identifier) @name) @func
            (type_item name: (type_identifier) @name) @type
            (mod_item name: (identifier) @name) @mod
        "#).expect("Error compiling tree-sitter query for Rust");

        for result in walker {
            let entry = match result {
                Ok(e) => e,
                Err(_) => continue,
            };

            let path = entry.path();
            if !path.is_file() {
                continue;
            }

            if path.extension().and_then(OsStr::to_str) != Some("rs") {
                continue; // Only Rust for now, can be extended easily for TS/Python
            }

            let source = match fs::read_to_string(path) {
                Ok(s) => s,
                Err(_) => continue,
            };

            let relative_path = path.strip_prefix(&self.root)
                .unwrap_or(path)
                .to_string_lossy()
                .to_string();

            let mut tags = Vec::new();
            if let Some(tree) = parser.parse(&source, None) {
                let mut cursor = QueryCursor::new();
                let mut captures = cursor.captures(&query, tree.root_node(), source.as_bytes());

                while let Some((m, _capture_index)) = captures.next() {
                    for capture in m.captures {
                        let node = capture.node;
                        let kind = node.kind();
                        if kind == "type_identifier" || kind == "identifier" {
                            let name = &source[node.start_byte()..node.end_byte()];
                            let parent = node.parent().unwrap();
                            let parent_kind = parent.kind();
                            
                            let prefix = match parent_kind {
                                "struct_item" => "struct",
                                "enum_item" => "enum",
                                "trait_item" => "trait",
                                "impl_item" => "impl",
                                "function_item" => "fn",
                                "type_item" => "type",
                                "mod_item" => "mod",
                                _ => "symbol",
                            };

                            tags.push(format!("{} {}", prefix, name));
                        }
                    }
                }
            }
            
            // Deduplicate safely while maintaining order
            let mut unique_tags = Vec::new();
            for tag in tags {
                if !unique_tags.contains(&tag) {
                    unique_tags.push(tag);
                }
            }

            map.files.insert(relative_path, unique_tags);
        }

        Ok(map)
    }
}
