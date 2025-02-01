import os
import re
import subprocess
from pathlib import Path
import argparse

def find_image_references(md_file):
    """Find all image references in a markdown file."""
    with open(md_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    pattern = r'!\[.*?\]\((.*?)\)'
    matches = re.findall(pattern, content)
    
    cleaned_paths = []
    for match in matches:
        path = match.lstrip('/')
        if 'img/' in path:
            path = path[path.index('img/') + 4:]
            # Only keep references to versioned images
            parts = os.path.normpath(path).split(os.sep)
            if len(parts) >= 2 and parts[0].replace('.', '').isdigit():
                cleaned_paths.append(path)
    
    return cleaned_paths

def scan_markdown_files(docs_dir):
    """Recursively scan all markdown files in the docs directory."""
    md_files = []
    for root, _, files in os.walk(docs_dir):
        for file in files:
            if file.endswith('.md'):
                md_files.append(os.path.join(root, file))
    return md_files

def find_all_images(img_dir):
    """Find all image files in version subdirectories."""
    image_files = []
    for root, _, files in os.walk(img_dir):
        # Get the relative path from img_dir to current directory
        rel_dir = os.path.relpath(root, img_dir)
        
        # Skip if we're in the root img directory
        if rel_dir == '.':
            continue
            
        # Check if the immediate parent directory is a version number
        parent_dir = rel_dir.split(os.sep)[0]
        if not parent_dir.replace('.', '').isdigit():
            continue
            
        for file in files:
            if file.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.svg')):
                rel_path = os.path.relpath(os.path.join(root, file), img_dir)
                image_files.append(rel_path)
    return image_files

def grep_check_image(docs_dir, image_path):
    """
    Check if versioned image is referenced anywhere using grep.
    Returns True if any reference is found, False otherwise.
    """
    try:
        # Split the image path to get version and filename
        parts = os.path.normpath(image_path).split(os.sep)
        version = parts[0]  # e.g., "0.29.0"
        filename = parts[-1]  # e.g., "world-state-suggestions-2.png"
        
        # For versioned images, require both version and filename to match
        version_pattern = f"{version}.*{filename}"
        try:
            result = subprocess.run(
                ['grep', '-r', '-l', version_pattern, docs_dir],
                capture_output=True,
                text=True
            )
            if result.stdout.strip():
                print(f"Found reference to {image_path} with version pattern: {version_pattern}")
                return True
        except subprocess.CalledProcessError:
            pass
            
    except Exception as e:
        print(f"Error during grep check for {image_path}: {e}")
    
    return False

def main():
    parser = argparse.ArgumentParser(description='Find and optionally delete unused versioned images in MkDocs project')
    parser.add_argument('--docs-dir', type=str, required=True, help='Path to the docs directory')
    parser.add_argument('--img-dir', type=str, required=True, help='Path to the images directory')
    parser.add_argument('--delete', action='store_true', help='Delete unused images')
    parser.add_argument('--verbose', action='store_true', help='Show all found references and files')
    parser.add_argument('--skip-grep', action='store_true', help='Skip the additional grep validation')
    args = parser.parse_args()

    # Convert paths to absolute paths
    docs_dir = os.path.abspath(args.docs_dir)
    img_dir = os.path.abspath(args.img_dir)

    print(f"Scanning markdown files in: {docs_dir}")
    print(f"Looking for versioned images in: {img_dir}")

    # Get all markdown files
    md_files = scan_markdown_files(docs_dir)
    print(f"Found {len(md_files)} markdown files")

    # Collect all image references
    used_images = set()
    for md_file in md_files:
        refs = find_image_references(md_file)
        used_images.update(refs)

    # Get all actual images (only from version directories)
    all_images = set(find_all_images(img_dir))

    if args.verbose:
        print("\nAll versioned image references found in markdown:")
        for img in sorted(used_images):
            print(f"- {img}")
        
        print("\nAll versioned images in directory:")
        for img in sorted(all_images):
            print(f"- {img}")

    # Find potentially unused images
    unused_images = all_images - used_images

    # Additional grep validation if not skipped
    if not args.skip_grep and unused_images:
        print("\nPerforming additional grep validation...")
        actually_unused = set()
        for img in unused_images:
            if not grep_check_image(docs_dir, img):
                actually_unused.add(img)
        
        if len(actually_unused) != len(unused_images):
            print(f"\nGrep validation found {len(unused_images) - len(actually_unused)} additional image references!")
        unused_images = actually_unused

    # Report findings
    print("\nResults:")
    print(f"Total versioned images found: {len(all_images)}")
    print(f"Versioned images referenced in markdown: {len(used_images)}")
    print(f"Unused versioned images: {len(unused_images)}")

    if unused_images:
        print("\nUnused versioned images:")
        for img in sorted(unused_images):
            print(f"- {img}")
            
        if args.delete:
            print("\nDeleting unused versioned images...")
            for img in unused_images:
                full_path = os.path.join(img_dir, img)
                try:
                    os.remove(full_path)
                    print(f"Deleted: {img}")
                except Exception as e:
                    print(f"Error deleting {img}: {e}")
            print("\nDeletion complete")
    else:
        print("\nNo unused versioned images found!")

if __name__ == "__main__":
    main()