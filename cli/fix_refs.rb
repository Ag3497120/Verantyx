require 'xcodeproj'
project = Xcodeproj::Project.open('Verantyx.xcodeproj')
target = project.targets.first
group = project.main_group.find_subpath('Sources/Verantyx/Engine', true)

# Remove all bad references
group.files.each do |f|
    if !File.exist?(f.real_path)
        puts "Removing missing file: #{f.path}"
        f.remove_from_project
    end
end

project.save
