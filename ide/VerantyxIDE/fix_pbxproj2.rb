require 'xcodeproj'
project_path = 'Verantyx.xcodeproj'
project = Xcodeproj::Project.open(project_path)

target = project.targets.first
views_group = project.main_group.find_subpath('Sources/Verantyx/Views', true)

unless views_group.files.find { |f| f.path == 'ExtensionUIPanelView.swift' }
    file_ref = views_group.new_reference('ExtensionUIPanelView.swift')
    target.add_file_references([file_ref])
    puts "Added ExtensionUIPanelView.swift to Views group"
end

project.save
