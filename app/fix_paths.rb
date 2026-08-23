require 'xcodeproj'
project = Xcodeproj::Project.open('Verantyx.xcodeproj')
target = project.targets.first

# Gatekeeper group has wrong path mapping?
gatekeeper_group = project.main_group.find_subpath('Sources/Verantyx/Gatekeeper', false)
if gatekeeper_group
    gatekeeper_group.set_path('Gatekeeper')
    gatekeeper_group.set_source_tree('<group>')
    puts "Fixed Gatekeeper group path"
end

# Check if the files are looking in the wrong place
project.files.each do |f|
    if f.path == 'JCrossVault.swift' || f.name == 'JCrossVault.swift'
        puts "Found JCrossVault: path=#{f.path}, source_tree=#{f.source_tree}"
        f.set_path('JCrossVault.swift')
        f.set_source_tree('<group>')
    end
end
project.save
