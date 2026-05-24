import { PCCrawler } from './src/verantyx/agents/scout/pc-crawler';

async function main() {
    const crawler = new PCCrawler();
    console.log("Generating PC Map...");
    const map = await crawler.generateMap();
    console.log(map);
}

main();
