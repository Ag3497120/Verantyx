require 'xcodeproj'
project_path = 'Verantyx.xcodeproj'
project = Xcodeproj::Project.open(project_path)

target = project.targets.first

group_path = 'Sources/Verantyx/Engine'
group = project.main_group.find_subpath(group_path, true)

files_to_add = [
    'Sources/Verantyx/Engine/ExtensionHostManager.swift',
    'Sources/Verantyx/Engine/VSIXPackageManager.swift',
    'Sources/Verantyx/Engine/CommandManager.swift',
    'Sources/Verantyx/Engine/LanguageManager.swift',
    'Sources/Verantyx/Engine/WorkspaceFileSystem.swift',
    'Sources/Verantyx/Views/ExtensionWebView.swift',
    'Sources/Verantyx/Engine/ExtensionUIManager.swift'
]

files_to_add.each do |file_path|
    next unless File.exist?(file_path)
    file_name = File.basename(file_path)
    
    # Check if file is already in the project
    unless group.files.find { |f| f.path == file_name }
        file_ref = group.new_reference(file_name)
        target.add_file_references([file_ref])
        puts "Added #{file_name} to project"
    end
end

project.save
