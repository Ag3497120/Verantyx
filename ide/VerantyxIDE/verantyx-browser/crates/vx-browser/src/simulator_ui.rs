pub const HTML_TEMPLATE: &str = r##"
<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <title>JCross Concept Telepathy Simulator</title>
    <style>
        body {
            margin: 0;
            padding: 0;
            background-color: #FAF9F6;
            color: #2D2D2D;
            font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            overflow: hidden;
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
        }
        canvas {
            display: block;
            width: 100%;
            height: 100%;
            position: absolute;
            z-index: 1;
        }
        #ui-layer {
            position: absolute;
            top: 24px;
            left: 28px;
            z-index: 10;
            pointer-events: none;
        }
        .title {
            font-size: 20px;
            font-weight: 500;
            color: #1A1A1A;
            letter-spacing: -0.01em;
            text-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
        }
        .subtitle {
            font-size: 13px;
            color: #71717A;
            margin-top: 4px;
            font-weight: 400;
        }
        #tooltip {
            position: absolute;
            background: #FFFFFF;
            border: 1px solid #E4E4E7;
            border-radius: 8px;
            padding: 12px 16px;
            color: #3F3F46;
            font-size: 13px;
            line-height: 1.5;
            z-index: 20;
            pointer-events: none;
            display: none;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -2px rgba(0, 0, 0, 0.05);
            max-width: 320px;
            white-space: pre-wrap;
        }
    </style>
</head>
<body>
    <div id="ui-layer">
        <div class="title">JCross Spatial Simulator</div>
        <div class="subtitle">Architect Hive - Concept Topology</div>
    </div>
    <div id="tooltip"></div>
    <canvas id="universe"></canvas>

    <script>
        const canvas = document.getElementById('universe');
        const ctx = canvas.getContext('2d');
        const tooltip = document.getElementById('tooltip');
        
        let width = window.innerWidth;
        let height = window.innerHeight;
        canvas.width = width;
        canvas.height = height;
        
        window.addEventListener('resize', () => {
            width = window.innerWidth;
            height = window.innerHeight;
            canvas.width = width;
            canvas.height = height;
        });

        let nodes = [];
        let links = [];

        // Force Directed Graph Physics Constants
        const REPULSION = 10000;
        const SPRING_LENGTH = 150;
        const SPRING_K = 0.05;
        const DAMPING = 0.85;

        let draggedNode = null;
        let hoveredNode = null;

        function updateGraph(data) {
            // Merge existing nodes to keep velocity
            const newNodesMap = new Map(data.nodes.map(n => [n.id, n]));
            
            const updatedNodes = [];
            for (const n of data.nodes) {
                const existing = nodes.find(old => old.id === n.id);
                if (existing) {
                    existing.label = n.label;
                    existing.axis = n.axis;
                    updatedNodes.push(existing);
                } else {
                    updatedNodes.push({
                        ...n,
                        x: width/2 + (Math.random() * 100 - 50),
                        y: height/2 + (Math.random() * 100 - 50),
                        vx: 0,
                        vy: 0
                    });
                }
            }
            nodes = updatedNodes;

            links = data.links.map(l => {
                return {
                    source: nodes.find(n => n.id === l.source),
                    target: nodes.find(n => n.id === l.target)
                };
            }).filter(l => l.source && l.target);
        }

        function tick() {
            for (let i = 0; i < nodes.length; i++) {
                for (let j = i + 1; j < nodes.length; j++) {
                    const n1 = nodes[i];
                    const n2 = nodes[j];
                    const dx = n2.x - n1.x;
                    const dy = n2.y - n1.y;
                    let dist = Math.sqrt(dx * dx + dy * dy);
                    if (dist === 0) dist = 0.01;
                    
                    const f = REPULSION / (dist * dist);
                    const fx = (dx / dist) * f;
                    const fy = (dy / dist) * f;
                    
                    n1.vx -= fx;
                    n1.vy -= fy;
                    n2.vx += fx;
                    n2.vy += fy;
                }
            }

            for (const link of links) {
                const n1 = link.source;
                const n2 = link.target;
                const dx = n2.x - n1.x;
                const dy = n2.y - n1.y;
                let dist = Math.sqrt(dx * dx + dy * dy);
                if (dist === 0) dist = 0.01;
                
                const f = (dist - SPRING_LENGTH) * SPRING_K;
                const fx = (dx / dist) * f;
                const fy = (dy / dist) * f;
                
                n1.vx += fx;
                n1.vy += fy;
                n2.vx -= fx;
                n2.vy -= fy;
            }

            for (const n of nodes) {
                const dx = (width / 2) - n.x;
                const dy = (height / 2) - n.y;
                n.vx += dx * 0.002;
                n.vy += dy * 0.002;
            }

            for (const n of nodes) {
                if (n !== draggedNode) {
                    n.x += n.vx;
                    n.y += n.vy;
                }
                n.vx *= DAMPING;
                n.vy *= DAMPING;
            }

            render();
            requestAnimationFrame(tick);
        }

        function getStyleForAxis(axis) {
            switch(axis) {
                case 'FRONT': return { color: '#D97757', glow: 'rgba(217, 119, 87, 0.4)' };
                case 'NEAR': return { color: '#60A5FA', glow: 'rgba(96, 165, 250, 0.3)' };
                case 'MID': return { color: '#34D399', glow: 'rgba(52, 211, 153, 0.2)' };
                case 'DEEP': return { color: '#A1A1AA', glow: 'rgba(161, 161, 170, 0.2)' };
                default: return { color: '#D4D4D8', glow: 'rgba(212, 212, 216, 0.2)' };
            }
        }

        function render() {
            ctx.clearRect(0, 0, width, height);

            ctx.lineWidth = 1.5;
            for (const link of links) {
                ctx.beginPath();
                ctx.moveTo(link.source.x, link.source.y);
                ctx.lineTo(link.target.x, link.target.y);
                const sStyle = getStyleForAxis(link.source.axis);
                ctx.strokeStyle = sStyle.glow;
                ctx.stroke();
            }

            for (const n of nodes) {
                const style = getStyleForAxis(n.axis);
                
                ctx.beginPath();
                ctx.arc(n.x, n.y, 8, 0, Math.PI * 2);
                ctx.shadowColor = style.color;
                ctx.shadowBlur = 12;
                ctx.fillStyle = hoveredNode === n ? '#1A1A1A' : style.color;
                ctx.fill();
                
                ctx.shadowBlur = 0;

                ctx.font = "11px ui-sans-serif, system-ui, sans-serif";
                ctx.fillStyle = "#52525B";
                ctx.fillText(n.id, n.x + 12, n.y + 4);
            }
        }

        canvas.addEventListener('mousemove', (e) => {
            const rect = canvas.getBoundingClientRect();
            const mouseX = e.clientX - rect.left;
            const mouseY = e.clientY - rect.top;

            if (draggedNode) {
                draggedNode.x = mouseX;
                draggedNode.y = mouseY;
                return;
            }

            let found = null;
            for (let i = nodes.length - 1; i >= 0; i--) {
                const n = nodes[i];
                const dx = n.x - mouseX;
                const dy = n.y - mouseY;
                if (dx*dx + dy*dy < 100) {
                    found = n;
                    break;
                }
            }

            if (found !== hoveredNode) {
                hoveredNode = found;
                if (hoveredNode) {
                    tooltip.style.display = 'block';
                    tooltip.style.left = (hoveredNode.x + 15) + 'px';
                    tooltip.style.top = (hoveredNode.y - 15) + 'px';
                    tooltip.textContent = `[${hoveredNode.axis}] ${hoveredNode.id}\n${hoveredNode.label}`;
                } else {
                    tooltip.style.display = 'none';
                }
            } else if (hoveredNode) {
                tooltip.style.left = (hoveredNode.x + 15) + 'px';
                tooltip.style.top = (hoveredNode.y - 15) + 'px';
            }
        });

        canvas.addEventListener('mousedown', (e) => {
            if (hoveredNode) {
                draggedNode = hoveredNode;
                draggedNode.vx = 0;
                draggedNode.vy = 0;
            }
        });

        window.addEventListener('mouseup', () => {
            draggedNode = null;
        });

        window.addEventListener('DOMContentLoaded', () => {
            if (window.ipc && window.ipc.postMessage) {
                window.ipc.postMessage('SIM_READY:1');
            }
        });

        window.loadJCrossData = function(payloadStr) {
            try {
                const data = JSON.parse(payloadStr);
                updateGraph(data);
            } catch(e) {
                console.error("Failed to parse JCross JSON payload", e);
            }
        };

        requestAnimationFrame(tick);
    </script>
</body>
</html>
"##;
