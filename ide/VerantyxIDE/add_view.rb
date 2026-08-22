require 'xcodeproj'
project_path = 'Verantyx.xcodeproj'
project = Xcodeproj::Project.open(project_path)
target = project.targets.first
group_path = 'Sources/Verantyx/Views'
group = project.main_group.find_subpath(group_path, true)
file_path = 'Sources/Verantyx/Views/ExtensionStoreView.swift'
file_name = File.basename(file_path)
unless group.files.find { |f| f.path == file_name }
    file_ref = group.new_reference(file_name)
    target.add_file_references([file_ref])
    puts "Added #{file_name} to project"
end
project.save
