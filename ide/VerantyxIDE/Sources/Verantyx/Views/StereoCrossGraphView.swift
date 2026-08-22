import SwiftUI
import SceneKit

// MARK: - StereoCrossGraphView
//
// Live 3D visualization of Vera's CrossStore, built from the original
// "stereo-cross" design: each core is a small center cube with 6 arms
// extending along the ±x/±y/±z axes. One arm's tip carries the core's
// name (its "meaning"); the other 5 arms carry small colored spheres for
// its top facets, sized by facet count. Multiple cores are arranged in a
// ring so the whole structure reads as a graph, not a single object.
//
// Data comes from `VeraMemoryBridge.fetchGraphSnapshot()` (the
// `graph_snapshot` MCP tool, Verantyx-Vera-alpha's mcp_server.py) --
// read-only, structural, never used for grounded QA.
//
// Approving a Vera-α save while this view is active
// (`AppState.pendingVeraSave`/`pendingGraphConnection`) plays a
// "connection" animation: a new marker travels from off-scene to the
// core it was saved against, visualizing what `remember`/
// `propose_ai_facts` actually did internally.

struct StereoCrossGraphView: View {
    @EnvironmentObject var app: AppState
    @State private var scene = SCNScene()
    @State private var coreNodeMap: [String: SCNNode] = [:]
    @State private var isLoading = true
    @State private var nodeCount = 0
    @State private var totalCores = 0
    @State private var errorMessage: String?

    private enum GraphMode: String, CaseIterable, Identifiable {
        case vera, uiTrace
        var id: String { rawValue }
    }
    @State private var mode: GraphMode = .vera
    /// Milestone G: renders a UI-testing/bug-repro session's per-step
    /// vector sequence (`UITestVectorTrace`) as a time-ordered stereo-cross
    /// path -- z = step index, reusing the z-as-time convention
    /// `JCross3DGraph.swift` established for a different feature, applied
    /// here to an actual SceneKit view for the first time.
    @State private var traceSessionId: String = ""
    @State private var isLoadingTrace = false

    var body: some View {
        ZStack {
            SceneKitHostView(scene: scene)

            VStack(spacing: 0) {
                header
                Spacer()
                if let errorMessage {
                    Text(errorMessage)
                        .font(.system(size: 11))
                        .foregroundStyle(Color(red: 1.0, green: 0.55, blue: 0.5))
                        .padding(8)
                        .frame(maxWidth: .infinity)
                        .background(Color.black.opacity(0.55))
                }
            }
        }
        .background(Color(red: 0.04, green: 0.04, blue: 0.07))
        .task { await loadGraph() }
        .onChange(of: app.pendingGraphConnection) { newValue in
            guard let label = newValue else { return }
            let focusCores = app.pendingGraphFocusCores
            Task {
                // A just-saved fact's core key (if we have one) may not be
                // in the currently-built scene yet -- graph_snapshot ranks
                // by pour count, so a brand-new fact loses to thousands of
                // already-accumulated cores unless explicitly requested via
                // focus_cores. Refresh first so the node actually exists
                // before trying to animate a connection onto it.
                if mode == .vera, !focusCores.isEmpty && focusCores.contains(where: { coreNodeMap[$0] == nil }) {
                    await loadGraph(focusCores: focusCores)
                }
                if mode == .vera {
                    animateConnection(for: label, preferredCores: focusCores)
                }
            }
        }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 10) {
                Image(systemName: "cube.transparent.fill")
                    .font(.system(size: 13))
                    .foregroundStyle(Color(red: 0.5, green: 0.8, blue: 1.0))

                Picker("", selection: $mode) {
                    Text(app.t("Vera Graph", "Veraグラフ")).tag(GraphMode.vera)
                    Text(app.t("UI Test Trace", "UIテスト・トレース")).tag(GraphMode.uiTrace)
                }
                .pickerStyle(.segmented)
                .labelsHidden()
                .frame(width: 220)

                if mode == .vera {
                    if isLoading {
                        ProgressView().controlSize(.small)
                    } else {
                        Text(app.t("\(nodeCount) of \(totalCores) cores", "\(totalCores)個中\(nodeCount)個の核"))
                            .font(.system(size: 10, design: .monospaced))
                            .foregroundStyle(Color(red: 0.6, green: 0.6, blue: 0.7))
                    }
                } else if isLoadingTrace {
                    ProgressView().controlSize(.small)
                } else {
                    Text(app.t("\(nodeCount) steps", "\(nodeCount)ステップ"))
                        .font(.system(size: 10, design: .monospaced))
                        .foregroundStyle(Color(red: 0.6, green: 0.6, blue: 0.7))
                }

                Spacer()

                Button {
                    Task {
                        if mode == .vera { await loadGraph(focusCores: []) }
                        else { await loadTrace() }
                    }
                } label: {
                    Image(systemName: "arrow.clockwise")
                        .font(.system(size: 11))
                        .foregroundStyle(Color(red: 0.6, green: 0.6, blue: 0.7))
                }
                .buttonStyle(.plain)
                .help(app.t("Refresh", "再読み込み"))
            }

            if mode == .uiTrace {
                HStack(spacing: 6) {
                    TextField(app.t("Session ID", "セッションID"), text: $traceSessionId)
                        .textFieldStyle(.roundedBorder)
                        .font(.system(size: 10, design: .monospaced))
                        .frame(width: 160)
                    Button(app.t("Load", "読み込む")) { Task { await loadTrace() } }
                        .buttonStyle(.bordered)
                        .controlSize(.small)
                        .disabled(traceSessionId.trimmingCharacters(in: .whitespaces).isEmpty)
                }
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .background(Color.black.opacity(0.4))
    }

    // MARK: - Data loading

    private func loadGraph(focusCores: [String] = []) async {
        isLoading = true
        errorMessage = nil
        guard let snapshot = await VeraMemoryBridge.fetchGraphSnapshot(focusCores: focusCores), !snapshot.nodes.isEmpty else {
            isLoading = false
            nodeCount = 0
            errorMessage = app.t(
                "Vera has nothing poured yet, or vera-memory isn't reachable.",
                "Veraにはまだ何も蓄積されていないか、vera-memoryに接続できません。"
            )
            return
        }
        let (builtScene, map) = Self.buildScene(from: snapshot)
        scene = builtScene
        coreNodeMap = map
        nodeCount = snapshot.nodes.count
        totalCores = snapshot.total_cores
        isLoading = false
    }

    /// Milestone G: loads and renders one UI-testing session's step
    /// sequence from `UITestVectorTrace` -- no Vera/graph_snapshot
    /// involved, entirely separate data source from `loadGraph`.
    private func loadTrace() async {
        let sessionId = traceSessionId.trimmingCharacters(in: .whitespaces)
        guard !sessionId.isEmpty else { return }
        isLoadingTrace = true
        errorMessage = nil
        let moments = await UITestVectorTrace.shared.trace(sessionId: sessionId)
        guard !moments.isEmpty else {
            isLoadingTrace = false
            nodeCount = 0
            errorMessage = app.t(
                "No recorded steps for this session yet.",
                "このセッションの記録されたステップはまだありません。"
            )
            return
        }
        scene = Self.buildTraceScene(from: moments)
        coreNodeMap = [:]
        nodeCount = moments.count
        totalCores = moments.count
        isLoadingTrace = false
    }

    // MARK: - Scene construction

    private static func buildScene(from snapshot: VeraMemoryBridge.GraphSnapshot) -> (SCNScene, [String: SCNNode]) {
        let scene = SCNScene()
        scene.background.contents = NSColor(calibratedRed: 0.04, green: 0.04, blue: 0.07, alpha: 1)

        let ambient = SCNNode()
        ambient.light = SCNLight()
        ambient.light!.type = .ambient
        ambient.light!.color = NSColor(white: 0.55, alpha: 1)
        scene.rootNode.addChildNode(ambient)

        let omni = SCNNode()
        omni.light = SCNLight()
        omni.light!.type = .omni
        omni.light!.color = NSColor.white
        omni.light!.intensity = 900
        omni.position = SCNVector3(0, 22, 24)
        scene.rootNode.addChildNode(omni)

        let cameraNode = SCNNode()
        cameraNode.camera = SCNCamera()
        cameraNode.camera?.zFar = 500
        let n = max(snapshot.nodes.count, 1)
        let radius = Float(7.0 + Double(n) * 0.55)
        cameraNode.position = SCNVector3(0, radius * 0.35, radius * 1.9)
        cameraNode.look(at: SCNVector3(0, 0, 0))
        scene.rootNode.addChildNode(cameraNode)

        var map: [String: SCNNode] = [:]
        for (i, node) in snapshot.nodes.enumerated() {
            let angle = (2.0 * Float.pi * Float(i)) / Float(n)
            let x = radius * cos(angle)
            let z = radius * sin(angle)
            let y = Float(i % 3 - 1) * 1.8
            let crossRoot = buildStereoCross(core: node.core, facets: node.facets)
            crossRoot.position = SCNVector3(x, y, z)
            scene.rootNode.addChildNode(crossRoot)
            map[node.core] = crossRoot
        }

        return (scene, map)
    }

    /// One "stereo-cross" unit: center cube + 6 arms. Arm 0's tip carries
    /// the core's name (its "meaning"); arms 1-5 carry a facet marker
    /// each, sized/colored by that facet's count -- matching the original
    /// design (tip = core meaning, sides/other arms = facets).
    private static func buildStereoCross(core: String, facets: [VeraMemoryBridge.GraphFacet]) -> SCNNode {
        let root = SCNNode()
        root.name = "cross:\(core)"

        let coreSize: CGFloat = 0.55
        let armLength: CGFloat = 1.05
        let armRadius: CGFloat = 0.07

        let cubeGeo = SCNBox(width: coreSize, height: coreSize, length: coreSize, chamferRadius: 0.06)
        cubeGeo.firstMaterial?.diffuse.contents = NSColor(calibratedRed: 0.3, green: 0.6, blue: 1.0, alpha: 1)
        cubeGeo.firstMaterial?.emission.contents = NSColor(calibratedRed: 0.08, green: 0.22, blue: 0.5, alpha: 1)
        root.addChildNode(SCNNode(geometry: cubeGeo))

        // Axis-aligned arm directions. SCNCylinder's height axis is Y by
        // default, so only ±x/±z need a 90° rotation; ±y needs none.
        let axes: [(offset: SCNVector3, rotation: SCNVector4?)] = [
            (SCNVector3(1, 0, 0), SCNVector4(0, 0, 1, Float.pi / 2)),   // +x
            (SCNVector3(-1, 0, 0), SCNVector4(0, 0, 1, Float.pi / 2)),  // -x
            (SCNVector3(0, 1, 0), nil),                                  // +y
            (SCNVector3(0, -1, 0), nil),                                 // -y
            (SCNVector3(0, 0, 1), SCNVector4(1, 0, 0, Float.pi / 2)),   // +z
            (SCNVector3(0, 0, -1), SCNVector4(1, 0, 0, Float.pi / 2)),  // -z
        ]

        for (i, axis) in axes.enumerated() {
            let armCenterDist = CGFloat(coreSize / 2 + armLength / 2)
            let tipDist = CGFloat(coreSize / 2 + armLength)

            let armGeo = SCNCylinder(radius: armRadius, height: armLength)
            armGeo.firstMaterial?.diffuse.contents = NSColor(calibratedRed: 0.5, green: 0.75, blue: 1.0, alpha: 0.85)
            let armNode = SCNNode(geometry: armGeo)
            armNode.position = SCNVector3(axis.offset.x * armCenterDist,
                                           axis.offset.y * armCenterDist,
                                           axis.offset.z * armCenterDist)
            if let rot = axis.rotation {
                armNode.rotation = rot
            }
            root.addChildNode(armNode)

            let tipPosition = SCNVector3(axis.offset.x * tipDist, axis.offset.y * tipDist, axis.offset.z * tipDist)

            if i == 0 {
                // Tip = core meaning
                let textGeo = SCNText(string: core, extrusionDepth: 0.1)
                textGeo.font = NSFont.systemFont(ofSize: 3)
                textGeo.flatness = 0.2
                textGeo.firstMaterial?.diffuse.contents = NSColor(calibratedRed: 0.95, green: 0.95, blue: 1.0, alpha: 1)
                textGeo.firstMaterial?.emission.contents = NSColor(calibratedRed: 0.3, green: 0.3, blue: 0.4, alpha: 1)
                let textNode = SCNNode(geometry: textGeo)
                textNode.scale = SCNVector3(0.11, 0.11, 0.11)
                let (minB, maxB) = textGeo.boundingBox
                let textWidth = CGFloat(maxB.x - minB.x) * 0.11
                textNode.position = SCNVector3(tipPosition.x - textWidth / 2, tipPosition.y + 0.2, tipPosition.z)
                textNode.constraints = [SCNBillboardConstraint()]
                root.addChildNode(textNode)
            } else if i - 1 < facets.count {
                // Sides = facets
                let facet = facets[i - 1]
                let scaledRadius = 0.10 + CGFloat(min(facet.count, 12)) * 0.018
                let sphereGeo = SCNSphere(radius: scaledRadius)
                let hue = CGFloat(abs(facet.facet.hashValue) % 360) / 360.0
                sphereGeo.firstMaterial?.diffuse.contents = NSColor(calibratedHue: hue, saturation: 0.65, brightness: 0.95, alpha: 1)
                sphereGeo.firstMaterial?.emission.contents = NSColor(calibratedHue: hue, saturation: 0.5, brightness: 0.3, alpha: 1)
                let sphereNode = SCNNode(geometry: sphereGeo)
                sphereNode.position = tipPosition
                sphereNode.name = "facet:\(facet.facet)"
                root.addChildNode(sphereNode)
            }
        }

        return root
    }

    /// Milestone G: lays out one node per recorded step along a spiral,
    /// with **z = stepIndex** (SceneKit depth axis) so the sequence reads
    /// as a path receding into the screen -- the "動画のように時系列を
    /// 立体十字構造体で見る" effect, built from tiny stored vectors/labels
    /// only (see `UITestVectorTrace`), never raw screenshot/video frames.
    /// Node color/size reflects whether `VisualDiffRegion` found a real
    /// changed region for that step (bigger visual change = more
    /// prominent node); consecutive steps are connected by a thin line.
    private static func buildTraceScene(from moments: [UITestVectorTrace.Moment]) -> SCNScene {
        let scene = SCNScene()
        scene.background.contents = NSColor(calibratedRed: 0.04, green: 0.04, blue: 0.07, alpha: 1)

        let ambient = SCNNode()
        ambient.light = SCNLight()
        ambient.light!.type = .ambient
        ambient.light!.color = NSColor(white: 0.55, alpha: 1)
        scene.rootNode.addChildNode(ambient)

        let omni = SCNNode()
        omni.light = SCNLight()
        omni.light!.type = .omni
        omni.light!.color = NSColor.white
        omni.light!.intensity = 900
        omni.position = SCNVector3(0, 12, 12)
        scene.rootNode.addChildNode(omni)

        let stepSpacing: Float = 2.2
        let spiralRadius: Float = 1.6
        let goldenAngle: Float = 2.399963 // ~137.5°, keeps a dense spiral legible

        var positions: [SCNVector3] = []
        var previousNode: SCNNode?
        for (i, moment) in moments.enumerated() {
            let angle = Float(i) * goldenAngle
            let x = spiralRadius * cos(angle)
            let y = spiralRadius * sin(angle)
            let z = -Float(moment.stepIndex) * stepSpacing
            let position = SCNVector3(x, y, z)
            positions.append(position)

            let node = buildStepNode(moment: moment)
            node.position = position
            scene.rootNode.addChildNode(node)

            if let previousNode {
                scene.rootNode.addChildNode(connectingLine(from: previousNode.position, to: position))
            }
            previousNode = node
        }

        let cameraNode = SCNNode()
        cameraNode.camera = SCNCamera()
        cameraNode.camera?.zFar = 500
        let lastZ = positions.last?.z ?? 0
        cameraNode.position = SCNVector3(0, 6, (lastZ) / 2 + 8)
        cameraNode.look(at: SCNVector3(0, 0, lastZ / 2))
        scene.rootNode.addChildNode(cameraNode)

        return scene
    }

    /// One step's marker: a small sphere (bigger + warmer when a real
    /// changed region was detected, dim + small for "no notable change"
    /// steps like app launches) with a floating text label of the action.
    private static func buildStepNode(moment: UITestVectorTrace.Moment) -> SCNNode {
        let root = SCNNode()
        root.name = "step:\(moment.stepIndex)"

        let hasChange = moment.changedRegion != nil
        let changeMagnitude: CGFloat = {
            guard let r = moment.changedRegion, r.count == 4 else { return 0 }
            return CGFloat(r[2] * r[3])
        }()
        let radius: CGFloat = hasChange ? 0.22 + min(changeMagnitude / 400_000, 0.35) : 0.14

        let sphereGeo = SCNSphere(radius: radius)
        let color = hasChange
            ? NSColor(calibratedRed: 1.0, green: 0.6, blue: 0.3, alpha: 1)
            : NSColor(calibratedRed: 0.5, green: 0.55, blue: 0.65, alpha: 1)
        sphereGeo.firstMaterial?.diffuse.contents = color
        sphereGeo.firstMaterial?.emission.contents = color.withAlphaComponent(0.35)
        root.addChildNode(SCNNode(geometry: sphereGeo))

        let textGeo = SCNText(string: moment.actionLabel, extrusionDepth: 0.05)
        textGeo.font = NSFont.systemFont(ofSize: 3)
        textGeo.flatness = 0.2
        textGeo.firstMaterial?.diffuse.contents = NSColor(calibratedRed: 0.9, green: 0.9, blue: 0.95, alpha: 1)
        let textNode = SCNNode(geometry: textGeo)
        textNode.scale = SCNVector3(0.09, 0.09, 0.09)
        textNode.position = SCNVector3(Float(radius) + 0.15, Float(radius) * 0.3, 0)
        textNode.constraints = [SCNBillboardConstraint()]
        root.addChildNode(textNode)

        return root
    }

    private static func connectingLine(from: SCNVector3, to: SCNVector3) -> SCNNode {
        let indices: [Int32] = [0, 1]
        let source = SCNGeometrySource(vertices: [from, to])
        let element = SCNGeometryElement(indices: indices, primitiveType: .line)
        let geometry = SCNGeometry(sources: [source], elements: [element])
        geometry.firstMaterial?.diffuse.contents = NSColor(calibratedRed: 0.4, green: 0.45, blue: 0.55, alpha: 0.6)
        return SCNNode(geometry: geometry)
    }

    // MARK: - Connection animation

    /// Plays when a Vera save is approved while this view is active
    /// (`AppState.pendingGraphConnection`). Prefers an exact match against
    /// `preferredCores` (the real core key(s) the store just saved under,
    /// from VeraMemoryBridge.performSave) since that's precise; falls back
    /// to a substring match against the label, then to any existing node,
    /// so the user still sees SOMETHING connect rather than silently
    /// doing nothing.
    private func animateConnection(for label: String, preferredCores: [String] = []) {
        defer {
            DispatchQueue.main.asyncAfter(deadline: .now() + 1.8) {
                if app.pendingGraphConnection == label {
                    app.pendingGraphConnection = nil
                    app.pendingGraphFocusCores = []
                }
            }
        }
        let lowerLabel = label.lowercased()
        let target = preferredCores.compactMap { coreNodeMap[$0] }.first
            ?? coreNodeMap.first(where: { lowerLabel.contains($0.key.lowercased()) })?.value
            ?? coreNodeMap.values.first
        guard let target else { return }

        let dx = CGFloat.random(in: -6...6)
        let dy = CGFloat.random(in: 4...7)
        let dz = CGFloat.random(in: -6...6)
        let start = SCNVector3(
            target.position.x + dx,
            target.position.y + dy,
            target.position.z + dz
        )

        let travelerGeo = SCNSphere(radius: 0.16)
        travelerGeo.firstMaterial?.diffuse.contents = NSColor(calibratedRed: 1.0, green: 0.8, blue: 0.3, alpha: 1)
        travelerGeo.firstMaterial?.emission.contents = NSColor(calibratedRed: 0.9, green: 0.6, blue: 0.1, alpha: 1)
        let traveler = SCNNode(geometry: travelerGeo)
        traveler.position = start
        traveler.opacity = 0
        scene.rootNode.addChildNode(traveler)

        let fadeIn = SCNAction.fadeIn(duration: 0.15)
        let move = SCNAction.move(to: target.position, duration: 1.1)
        move.timingMode = .easeInEaseOut
        let arrive = SCNAction.run { [weak target] _ in
            guard let target else { return }
            let pulse = SCNAction.sequence([
                SCNAction.scale(to: 1.3, duration: 0.12),
                SCNAction.scale(to: 1.0, duration: 0.2),
            ])
            target.childNodes.first?.runAction(pulse)
        }
        let fadeOut = SCNAction.fadeOut(duration: 0.3)
        let remove = SCNAction.removeFromParentNode()
        traveler.runAction(.sequence([fadeIn, .group([move, .sequence([.wait(duration: 0.9), arrive])]), fadeOut, remove]))
    }
}

// MARK: - SceneKitHostView (NSViewRepresentable)

private struct SceneKitHostView: NSViewRepresentable {
    let scene: SCNScene

    func makeNSView(context: Context) -> SCNView {
        let view = SCNView()
        view.scene = scene
        view.allowsCameraControl = true
        view.autoenablesDefaultLighting = false
        view.backgroundColor = NSColor(calibratedRed: 0.04, green: 0.04, blue: 0.07, alpha: 1)
        view.antialiasingMode = .multisampling4X
        return view
    }

    func updateNSView(_ nsView: SCNView, context: Context) {
        if nsView.scene !== scene {
            nsView.scene = scene
        }
    }
}
