require 'xcodeproj'
project = Xcodeproj::Project.open('Verantyx.xcodeproj')
target = project.targets.first
engine_group = project.main_group.find_subpath('Sources/Verantyx/Engine', true)
views_group = project.main_group.find_subpath('Sources/Verantyx/Views', true)
gatekeeper_group = project.main_group.find_subpath('Sources/Verantyx/Gatekeeper', true)

files = [
    "Sources/Verantyx/Engine/BitNetEngine.swift",
    "Sources/Verantyx/Engine/BrowserBridgePool.swift",
    "Sources/Verantyx/Engine/CommandManager.swift",
    "Sources/Verantyx/Engine/ConfusionDetector.swift",
    "Sources/Verantyx/Engine/ExtensionHostManager.swift",
    "Sources/Verantyx/Engine/ExtensionUIManager.swift",
    "Sources/Verantyx/Engine/GitEngine.swift",
    "Sources/Verantyx/Engine/IRVerificationEngine.swift",
    "Sources/Verantyx/Engine/JCrossCodeTranspiler.swift",
    "Sources/Verantyx/Engine/JCrossIRParser.swift",
    "Sources/Verantyx/Engine/JCrossSchemaGenerator.swift",
    "Sources/Verantyx/Engine/LSPClient.swift",
    "Sources/Verantyx/Engine/LanguageManager.swift",
    "Sources/Verantyx/Engine/MCPBridgeLauncher.swift",
    "Sources/Verantyx/Engine/MCPCatalog.swift",
    "Sources/Verantyx/Engine/OllamaNEREngine.swift",
    "Sources/Verantyx/Engine/PreflightSearchEngine.swift",
    "Sources/Verantyx/Engine/ProjectSearchEngine.swift",
    "Sources/Verantyx/Engine/ReActRetryEngine.swift",
    "Sources/Verantyx/Engine/SearchGate.swift",
    "Sources/Verantyx/Engine/SearchIntentClassifier.swift",
    "Sources/Verantyx/Engine/VSIXPackageManager.swift",
    "Sources/Verantyx/Engine/VXTimeline.swift",
    "Sources/Verantyx/Engine/WorkspaceFileSystem.swift",
    "Sources/Verantyx/Gatekeeper/JCrossVault.swift",
    "Sources/Verantyx/Views/ExtensionStoreView.swift",
    "Sources/Verantyx/Views/ExtensionUIPanelView.swift",
    "Sources/Verantyx/Views/ExtensionWebView.swift",
    "Sources/Verantyx/Views/GitPanelView.swift",
    "Sources/Verantyx/Views/GlobalSearchView.swift",
    "Sources/Verantyx/Views/HumanPriorityModeView.swift",
    "Sources/Verantyx/Views/LoadedModelPanel.swift"
]

files.each do |f|
    file_name = File.basename(f)
    if f.include?('Gatekeeper')
        group = gatekeeper_group
    elsif f.include?('Views')
        group = views_group
    else
        group = engine_group
    end
    
    unless group.files.find { |file| file.path == file_name }
        file_ref = group.new_reference(file_name)
        target.add_file_references([file_ref])
    end
end
project.save
