require 'xcodeproj'
project = Xcodeproj::Project.open('Verantyx.xcodeproj')
target = project.targets.first

gatekeeper_group = project.main_group.find_subpath('Sources/Verantyx/Gatekeeper', true)

files = [
    "GatekeeperModeState.swift",
    "GatekeeperModeView.swift",
    "GatekeeperMCPServer.swift",
    "GatekeeperStatusPill.swift",
    "RoutingSessionLogger.swift",
    "SimpleJCrossTranspiler.swift",
    "AdversarialNoiseEngine.swift",
    "ClaudeSystemPromptBuilder.swift",
    "JCrossPatchValidator.swift"
]

files.each do |f|
    unless gatekeeper_group.files.find { |file| file.path == f }
        file_ref = gatekeeper_group.new_reference(f)
        target.add_file_references([file_ref])
    end
end
project.save
