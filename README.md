"# ai\_tessl"





\## Comannds



tessl inventory import --org sibendu --repo repo-a --repo repo-b --repo repo-c



tessl inventory import --org sibendu --ignore-repo old-experiment --ignore-repo scratch-repo



If you just want to preview what would be scanned/uploaded before committing, add --dry-run <path> to write the inventory JSON locally instead of uploading:



tessl inventory import --org sibendu --workspace sdas --repo repo-a --repo repo-b --dry-run ./inventory.json



