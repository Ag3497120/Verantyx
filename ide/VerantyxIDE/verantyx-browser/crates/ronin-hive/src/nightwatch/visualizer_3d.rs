use std::io::Write;

pub fn generate_3d_html(json_data: &serde_json::Value) {
    let html_path = std::env::current_dir().unwrap().join(".ronin").join("crucible_3d.html");
    
    // We inject the JSON payload directly into the JS logic so Three.js can parse the Kanji tags and abstract_level
    let json_string = serde_json::to_string(json_data).unwrap_or_else(|_| "{}".to_string());
    
    let html_content = format!(r#"
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Vera Lab: 3D Crucible</title>
    <style>
        body {{ margin: 0; overflow: hidden; background-color: #0b0f19; color: #fff; font-family: 'Courier New', Courier, monospace; }}
        #info-panel {{
            position: absolute; top: 20px; left: 20px;
            background: rgba(11, 15, 25, 0.85); padding: 20px;
            border: 1px solid #ffd54f; border-radius: 8px;
            max-width: 400px; z-index: 10;
            box-shadow: 0 0 15px rgba(255, 213, 79, 0.3);
        }}
        h2 {{ margin-top: 0; color: #ffd54f; font-size: 1.2rem; text-transform: uppercase; letter-spacing: 2px; }}
        .json-block {{
            background: rgba(0,0,0,0.5); padding: 10px;
            border-left: 3px solid #81c784; font-size: 0.9rem;
            white-space: pre-wrap; word-wrap: break-word;
            margin-top: 15px; color: #eee;
        }}
        .tag {{ display: inline-block; padding: 3px 8px; background: rgba(255,213,79,0.2); border: 1px solid #ffd54f; border-radius: 4px; margin-right: 5px; margin-bottom: 5px; font-size: 0.8rem; }}
    </style>
    <!-- Three.js CDN for 3D Rendering -->
    <script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"></script>
</head>
<body>

    <div id="info-panel">
        <h2>Crucible Synthesis Complete</h2>
        <div id="tags-container"></div>
        <div class="json-block" id="explanation"></div>
        <div style="margin-top: 15px; color: #64b5f6; font-size: 0.8rem;">Vision Core Prompt:</div>
        <div class="json-block" id="vision-prompt" style="border-left-color: #64b5f6; font-style: italic;"></div>
    </div>

    <script>
        const data = {};

        // Populate UI
        const jcross = data.synthesized_jcross || {{}};
        document.getElementById('explanation').innerText = data.explanation || "No explanation provided.";
        document.getElementById('vision-prompt').innerText = data.vision_prompt || "No prompt provided.";
        
        const tagsContainer = document.getElementById('tags-container');
        if (jcross.kanji_tags) {{
            jcross.kanji_tags.forEach(tag => {{
                const span = document.createElement('span');
                span.className = 'tag';
                span.innerText = tag;
                tagsContainer.appendChild(span);
            }});
        }}

        // --- Three.js 3D Engine Setup ---
        const scene = new THREE.Scene();
        scene.fog = new THREE.FogExp2(0x0b0f19, 0.02);

        const camera = new THREE.PerspectiveCamera(75, window.innerWidth / window.innerHeight, 0.1, 1000);
        camera.position.set(0, 15, 30);

        const renderer = new THREE.WebGLRenderer({{ antialias: true, alpha: true }});
        renderer.setSize(window.innerWidth, window.innerHeight);
        document.body.appendChild(renderer.domElement);

        const controls = new THREE.OrbitControls(camera, renderer.domElement);
        controls.enableDamping = true;
        controls.autoRotate = true;
        controls.autoRotateSpeed = 1.0;

        // Lighting
        const ambientLight = new THREE.AmbientLight(0xffffff, 0.2);
        scene.add(ambientLight);
        
        const pointLight = new THREE.PointLight(0xffd54f, 1.5, 100);
        pointLight.position.set(0, 10, 0);
        scene.add(pointLight);

        const pointLight2 = new THREE.PointLight(0x81c784, 1.0, 100);
        pointLight2.position.set(20, -10, 20);
        scene.add(pointLight2);

        // Grid Helper (Cyberpunk aesthetic)
        const gridHelper = new THREE.GridHelper(100, 50, 0x00ff00, 0x111111);
        gridHelper.position.y = -10;
        gridHelper.material.opacity = 0.2;
        gridHelper.material.transparent = true;
        scene.add(gridHelper);

        // Core Architectural Geometry based on Abstract Level
        // Abstract level dictates size and altitude
        const absLvl = jcross.abstract_level || 0.5;
        
        // Let's create a core monolith
        const coreGeo = new THREE.IcosahedronGeometry(5 + (absLvl * 5), 1);
        const coreMat = new THREE.MeshPhysicalMaterial({{
            color: 0xffd54f,
            emissive: 0x664400,
            wireframe: true,
            transparent: true,
            opacity: 0.8,
            roughness: 0.1,
            metalness: 0.8
        }});
        const coreMesh = new THREE.Mesh(coreGeo, coreMat);
        coreMesh.position.y = absLvl * 10;
        scene.add(coreMesh);

        // Generate orbiting particles representing Kanji dependencies
        const particles = new THREE.Object3D();
        const tagsCount = (jcross.kanji_tags || []).length;
        
        for(let i=0; i<150; i++) {{
            const mesh = new THREE.Mesh(
                new THREE.SphereGeometry(Math.random() * 0.5 + 0.1, 8, 8),
                new THREE.MeshBasicMaterial({{
                    color: i % 2 === 0 ? 0x81c784 : 0x64b5f6,
                    transparent: true,
                    opacity: Math.random() * 0.8 + 0.2
                }})
            );
            
            mesh.position.set(
                (Math.random() - 0.5) * 40,
                (Math.random() - 0.5) * 40,
                (Math.random() - 0.5) * 40
            );
            particles.add(mesh);
        }}
        scene.add(particles);

        // Connect particles with Cyber-lines if [結] or similar tag exists
        const hasConnectTag = (jcross.kanji_tags || []).some(t => t.includes('結') || t.includes('統'));
        if (hasConnectTag) {{
            const lineMat = new THREE.LineBasicMaterial({{ color: 0x4fc3f7, transparent: true, opacity: 0.15 }});
            const lineGeo = new THREE.BufferGeometry();
            const points = [];
            
            // Just connect some random particles to the core
            particles.children.forEach((p, idx) => {{
                if (idx % 3 === 0) {{
                    points.push(coreMesh.position);
                    points.push(p.position);
                }}
            }});
            lineGeo.setFromPoints(points);
            const lines = new THREE.LineSegments(lineGeo, lineMat);
            scene.add(lines);
        }}

        // Animation Loop
        const clock = new THREE.Clock();
        function animate() {{
            requestAnimationFrame(animate);
            const time = clock.getElapsedTime();
            
            controls.update();

            coreMesh.rotation.y += 0.005;
            coreMesh.rotation.x += 0.002;
            
            // Pulse emissive
            coreMesh.material.emissiveIntensity = 0.5 + Math.sin(time * 2) * 0.5;

            particles.rotation.y -= 0.001;
            particles.rotation.z += 0.0005;

            renderer.render(scene, camera);
        }}
        animate();

        window.addEventListener('resize', () => {{
            camera.aspect = window.innerWidth / window.innerHeight;
            camera.updateProjectionMatrix();
            renderer.setSize(window.innerWidth, window.innerHeight);
        }});
    </script>
</body>
</html>
"#, json_string);

    if let Ok(mut file) = std::fs::File::create(&html_path) {
        let _ = file.write_all(html_content.as_bytes());
        println!();
        #[cfg(target_os = "macos")]
        let _ = std::process::Command::new("open").arg(&html_path).spawn();
        #[cfg(target_os = "windows")]
        let _ = std::process::Command::new("cmd").args(&["/C", "start", html_path.to_str().unwrap()]).spawn();
        #[cfg(target_os = "linux")]
        let _ = std::process::Command::new("xdg-open").arg(&html_path).spawn();
    }
}
