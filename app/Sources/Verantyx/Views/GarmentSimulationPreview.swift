import SceneKit
import SwiftUI

/// SceneKit preview for a pending deterministic garment result. The approved
/// mesh is shown as a faint wire reference and the pending mesh as a solid;
/// this view never mutates either snapshot.
struct GarmentSimulationPreview: View {
    let before: GarmentMeshPreview?
    let after: GarmentMeshPreview?

    var body: some View {
        Group {
            if before?.isRenderable == true || after?.isRenderable == true {
                SceneView(
                    scene: Self.scene(before: before, after: after),
                    pointOfView: nil,
                    options: [.allowsCameraControl, .autoenablesDefaultLighting])
                    .background(Color.black.opacity(0.22))
                    .overlay(alignment: .topLeading) {
                        Text("3D PREVIEW · drag to orbit")
                            .font(.system(size: 8.5, weight: .semibold, design: .monospaced))
                            .foregroundStyle(Theme.faint)
                            .padding(7)
                    }
            } else {
                VStack(spacing: 6) {
                    Image(systemName: "cube.transparent")
                        .font(.system(size: 25)).foregroundStyle(Theme.faint)
                    Text("UNKNOWN_NO_PREVIEW_MESH")
                        .font(.system(size: 9.5, design: .monospaced))
                        .foregroundStyle(Theme.faint)
                    Text("The engine returned no indexed mesh.")
                        .font(.system(size: 10)).foregroundStyle(Theme.dim)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .background(Theme.panel2)
            }
        }
        .frame(height: 190)
        .clipShape(RoundedRectangle(cornerRadius: 8))
        .overlay(RoundedRectangle(cornerRadius: 8).stroke(Theme.faint.opacity(0.25)))
    }

    private static func scene(before: GarmentMeshPreview?,
                              after: GarmentMeshPreview?) -> SCNScene {
        let scene = SCNScene()
        let root = SCNNode()
        scene.rootNode.addChildNode(root)
        if let before, before.isRenderable {
            root.addChildNode(node(for: before, color: .systemGray,
                                   transparency: 0.28, wireframe: true))
        }
        if let after, after.isRenderable {
            root.addChildNode(node(for: after, color: .systemTeal,
                                   transparency: 0.82, wireframe: false))
        }
        fit(root: root, scene: scene)
        return scene
    }

    private static func node(for mesh: GarmentMeshPreview, color: NSColor,
                             transparency: CGFloat, wireframe: Bool) -> SCNNode {
        let scale = displayScale(for: mesh.vertices)
        let vertices = mesh.vertices.map {
            SCNVector3(Float($0[0] * scale), Float($0[1] * scale), Float($0[2] * scale))
        }
        var triangleIndices: [Int32] = []
        for face in mesh.faces where face.count >= 3 {
            for index in 1..<(face.count - 1) {
                triangleIndices.append(Int32(face[0]))
                triangleIndices.append(Int32(face[index]))
                triangleIndices.append(Int32(face[index + 1]))
            }
        }
        let source = SCNGeometrySource(vertices: vertices)
        let element = SCNGeometryElement(indices: triangleIndices, primitiveType: .triangles)
        let geometry = SCNGeometry(sources: [source], elements: [element])
        let material = SCNMaterial()
        material.diffuse.contents = color
        material.emission.contents = color.withAlphaComponent(0.08)
        material.transparency = transparency
        material.isDoubleSided = true
        material.fillMode = wireframe ? .lines : .fill
        material.lightingModel = .physicallyBased
        material.roughness.contents = 0.72
        geometry.materials = [material]
        return SCNNode(geometry: geometry)
    }

    /// Python geometry is usually centimetres for a second skin and metres for
    /// cloth simulation. SceneKit is unitless, so normalize only for display.
    private static func displayScale(for vertices: [[Double]]) -> Double {
        let maxMagnitude = vertices.flatMap { $0 }.map(abs).max() ?? 1
        return maxMagnitude > 10 ? 0.01 : 1.0
    }

    private static func fit(root: SCNNode, scene: SCNScene) {
        let (minimum, maximum) = root.boundingBox
        let center = SCNVector3((minimum.x + maximum.x) / 2,
                                (minimum.y + maximum.y) / 2,
                                (minimum.z + maximum.z) / 2)
        root.pivot = SCNMatrix4MakeTranslation(center.x, center.y, center.z)
        let extent = max(max(maximum.x - minimum.x, maximum.y - minimum.y),
                         maximum.z - minimum.z)
        let distance = max(extent * 2.2, 1.8)
        let camera = SCNNode()
        camera.camera = SCNCamera()
        camera.camera?.zNear = 0.001
        camera.camera?.zFar = Double(max(distance * 20, 100))
        camera.position = SCNVector3(0, 0, distance)
        scene.rootNode.addChildNode(camera)
        scene.background.contents = NSColor.windowBackgroundColor.withAlphaComponent(0.35)
    }
}
