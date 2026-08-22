use git2::{Repository, Signature, IndexAddOption, ResetType};
use std::path::Path;
use tracing::{info, warn};

pub struct GitEngine {
    repo: Repository,
}

impl GitEngine {
    pub fn new(workspace_root: impl AsRef<Path>) -> anyhow::Result<Self> {
        let repo = Repository::open(workspace_root)?;
        Ok(Self { repo })
    }

    /// Checks out a new branch for the agent. If it already exists, resets it.
    pub fn checkout_branch(&self, branch_name: &str) -> anyhow::Result<()> {
        let head = self.repo.head()?.peel_to_commit()?;
        
        let branch = match self.repo.find_branch(branch_name, git2::BranchType::Local) {
            Ok(b) => b,
            Err(_) => self.repo.branch(branch_name, &head, false)?,
        };

        let obj = branch.get().peel(git2::ObjectType::Tree)?;
        self.repo.checkout_tree(&obj, None)?;
        self.repo.set_head(branch.get().name().unwrap())?;

        info!("[Git] Checked out branch: {}", branch_name);
        Ok(())
    }

    /// Stages all changes and commits them with the given message.
    pub fn commit_all(&self, message: &str, author_name: &str, author_email: &str) -> anyhow::Result<()> {
        let mut index = self.repo.index()?;
        
        // Add all changed files inside the working tree
        index.add_all(["*"].iter(), IndexAddOption::DEFAULT, None)?;
        index.write()?;
        
        let oid = index.write_tree()?;
        let tree = self.repo.find_tree(oid)?;

        let sig = Signature::now(author_name, author_email)?;
        let parent_commit = self.repo.head()?.peel_to_commit()?;

        self.repo.commit(
            Some("HEAD"), // Update HEAD
            &sig,
            &sig,
            message,
            &tree,
            &[&parent_commit],
        )?;

        info!("[Git] Committed all changes: {}", message);
        Ok(())
    }

    /// Reverts current uncommitted changes by doing a hard reset to HEAD.
    pub fn revert_head(&self) -> anyhow::Result<()> {
        let head = self.repo.head()?.peel_to_commit()?;
        let obj = head.as_object();
        self.repo.reset(&obj, ResetType::Hard, None)?;
        warn!("[Git] Reverted uncommitted changes back to HEAD");
        Ok(())
    }
}
