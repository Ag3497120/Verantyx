require 'xcodeproj'
project = Xcodeproj::Project.open('Verantyx.xcodeproj')
target = project.targets.first

# Remove broken reference from Engine
engine_group = project.main_group.find_subpath('Sources/Verantyx/Engine', true)
engine_group.files.each do |f|
    if f.path == 'ExtensionWebView.swift'
        f.remove_from_project
    end
end

# Add correctly to Views
views_group = project.main_group.find_subpath('Sources/Verantyx/Views', true)
unless views_group.files.find { |f| f.path == 'ExtensionWebView.swift' }
    file_ref = views_group.new_reference('ExtensionWebView.swift')
    target.add_file_references([file_ref])
end
project.save
