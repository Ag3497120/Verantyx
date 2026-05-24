//! Terminal splash banner and status display utilities.

use console::style;

pub fn print_banner() {
    println!();
    println!("{}", style("██████╗  ██████╗ ███╗   ██╗██╗███╗   ██╗").cyan().bold());
    println!("{}", style("██╔══██╗██╔═══██╗████╗  ██║██║████╗  ██║").cyan().bold());
    println!("{}", style("██████╔╝██║   ██║██╔██╗ ██║██║██╔██╗ ██║").cyan().bold());
    println!("{}", style("██╔══██╗██║   ██║██║╚██╗██║██║██║╚██╗██║").cyan().dim());
    println!("{}", style("██║  ██║╚██████╔╝██║ ╚████║██║██║ ╚████║").cyan().dim());
    println!("{}", style("╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═══╝╚═╝╚═╝  ╚═══╝").cyan().dim());
    println!();
    println!(
        "  {} {} {}",
        style("🐺 Autonomous Hacker Agent").bold(),
        style("·").dim(),
        style("Local-First · Memory-Native · Policy-Safe").dim()
    );
    println!();
}

pub fn print_config_summary(model: &str, hitl: bool, lang: &str, steps: u32) {
    println!("{}", style("─".repeat(56)).dim());
    println!(
        "  {:<18} {}",
        style("[CORE_SLM]").dim(),
        style(model).green().bold()
    );
    println!(
        "  {:<18} {}",
        style("[HUMAN_IN_THE_LOOP]").dim(),
        if hitl { style("ACTIVE").green() } else { style("DISABLED").red() }
    );
    println!(
        "  {:<18} {}",
        style("[SYS_LANG]").dim(),
        style(lang).cyan()
    );
    println!(
        "  {:<18} {}",
        style("[MAX_RECURSION]").dim(),
        style(steps.to_string()).white()
    );
    println!("{}", style("─".repeat(56)).dim());
    println!();
}

pub fn print_step_header(step: u32, total: u32, description: &str) {
    println!(
        "\n{} {} {}",
        style(format!("[{}/{}]", step, total)).cyan().bold(),
        style("▶").green(),
        style(description).bold()
    );
}

pub fn print_observation(observation: &str) {
    println!();
    println!("{}", style("╔═ [OBSERVATION_DATA] ═══════════════════════════").dim());
    for line in observation.lines().take(40) {
        println!("{} {}", style("║").dim(), line);
    }
    println!("{}", style("╚════════════════════════════════════════════════").dim());
}

pub fn print_success(message: &str) {
    println!("\n{} {}", style("[OK]").green().bold(), style(message).bold());
}

pub fn print_warning(message: &str) {
    println!("\n{} {}", style("[WARN]").yellow().bold(), style(message).yellow());
}

pub fn print_error(message: &str) {
    println!("\n{} {}", style("[FAIL]").red().bold(), style(message).red().bold());
}
