require 'xcodeproj'
project_path = 'Verantyx.xcodeproj'
project = Xcodeproj::Project.open(project_path)

target = project.targets.first
engine_group = project.main_group.find_subpath('Sources/Verantyx/Engine', true)
views_group = project.main_group.find_subpath('Sources/Verantyx/Views', true)

# Remove ExtensionWebView.swift from Engine
engine_group.files.each do |f|
    if f.path == 'ExtensionWebView.swift'
        f.remove_from_project
        puts "Removed ExtensionWebView.swift from Engine group"
    end
end

# Add ExtensionWebView.swift to Views
unless views_group.files.find { |f| f.path == 'ExtensionWebView.swift' }
    file_ref = views_group.new_reference('ExtensionWebView.swift')
    target.add_file_references([file_ref])
    puts "Added ExtensionWebView.swift to Views group"
end

project.save
