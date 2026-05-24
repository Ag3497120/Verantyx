mod server;
mod routes;
mod models;

#[tokio::main]
async fn main() {
    println!("Starting PolyChat Backend...");
    server::start().await;
}
