require 'xcodeproj'
project_path = 'Verantyx.xcodeproj'
project = Xcodeproj::Project.open(project_path)
target = project.targets.first

file_path = ARGV[0]

# Check if file is already in the project
existing_file = project.files.find { |f| f.path == file_path || f.real_path.to_s.end_with?(file_path) }
if existing_file
  puts "File already exists in project."
else
  # Find or create group
  group = project.main_group.find_subpath(File.dirname(file_path), true)
  file_ref = group.new_reference(File.basename(file_path))
  target.add_file_references([file_ref])
  project.save
  puts "File added to project."
end
