require 'xcodeproj'
project = Xcodeproj::Project.open('Verantyx.xcodeproj')
target = project.targets.first

gatekeeper_group = project.main_group.find_subpath('Sources/Verantyx/Gatekeeper', true)

unless gatekeeper_group.files.find { |file| file.path == 'CommanderOrchestrator.swift' }
    file_ref = gatekeeper_group.new_reference('CommanderOrchestrator.swift')
    target.add_file_references([file_ref])
end
project.save
