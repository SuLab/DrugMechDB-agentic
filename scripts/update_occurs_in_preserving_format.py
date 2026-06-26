#!/usr/bin/env python3
"""
Script to update links in indication_paths.yaml while preserving original formatting.
Uses text-based processing with YAML parsing for validation.

Updates links where:
- key is "occurs in"
- source node has label "PhenotypicFeature"
- target node has label "Disease"

Changes the key to "phenotype of" for matching links.
"""

import yaml
import re
import sys
from typing import Dict, List, Any, Set


def load_yaml_file(filepath: str) -> List[Dict[str, Any]]:
    """Load the YAML file containing indication paths."""
    with open(filepath, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)
    return data


def get_node_label(nodes: List[Dict[str, Any]], node_id: str) -> str:
    """Get the label of a node by its ID."""
    for node in nodes:
        if node.get('id') == node_id:
            return node.get('label', '')
    return ''


def find_links_to_update(data: List[Dict[str, Any]]) -> Set[tuple]:
    """
    Find all links that need to be updated.
    Returns a set of (source_id, target_id) tuples.
    """
    links_to_update = set()

    for path in data:
        nodes = path.get('nodes', [])
        links = path.get('links', [])

        for link in links:
            key = link.get('key', '')
            source_id = link.get('source', '')
            target_id = link.get('target', '')

            if key == "occurs in":
                source_label = get_node_label(nodes, source_id)
                target_label = get_node_label(nodes, target_id)

                if source_label == "PhenotypicFeature" and target_label == "Disease":
                    links_to_update.add((source_id, target_id))

    return links_to_update


def update_file_preserving_format(filepath: str, links_to_update: Set[tuple]) -> int:
    """
    Update the file using text replacement to preserve formatting.
    Returns the number of changes made.
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    changes_count = 0
    i = 0

    while i < len(lines):
        line = lines[i]

        # Look for "key: occurs in" lines
        if 'key: occurs in' in line:
            # Check if this is followed by source and target that match our criteria
            # Look ahead to find source and target
            source_id = None
            target_id = None

            # Look at next few lines for source and target
            for j in range(i + 1, min(i + 5, len(lines))):
                next_line = lines[j]

                if 'source:' in next_line:
                    # Extract the source ID
                    match = re.search(r'source:\s+(.+)', next_line)
                    if match:
                        source_id = match.group(1).strip()

                if 'target:' in next_line:
                    # Extract the target ID
                    match = re.search(r'target:\s+(.+)', next_line)
                    if match:
                        target_id = match.group(1).strip()

                # If we found both, check if they match our criteria
                if source_id and target_id:
                    if (source_id, target_id) in links_to_update:
                        # Update this line
                        lines[i] = line.replace('key: occurs in', 'key: phenotype of')
                        changes_count += 1
                        print(f"Updated line {i + 1}: {source_id} -> {target_id}")
                    break

        i += 1

    # Write the updated content back
    with open(filepath, 'w', encoding='utf-8') as f:
        f.writelines(lines)

    return changes_count


def main():
    input_file = '/home/asu/Science/DrugMechDB.main/indication_paths.yaml'
    backup_file = '/home/asu/Science/DrugMechDB.main/indication_paths.yaml.backup2'

    print("Loading indication_paths.yaml to identify links to update...")
    try:
        data = load_yaml_file(input_file)
        print(f"Loaded {len(data)} paths.\n")
    except Exception as e:
        print(f"Error loading file: {e}")
        sys.exit(1)

    print("Identifying links to update...")
    links_to_update = find_links_to_update(data)
    print(f"Found {len(links_to_update)} unique links to update.\n")

    if len(links_to_update) == 0:
        print("No changes needed - no matching links found.")
        return

    # Create backup
    print(f"Creating backup at {backup_file}...")
    import shutil
    shutil.copy(input_file, backup_file)

    # Update the file while preserving formatting
    print("Updating file while preserving formatting...\n")
    changes_count = update_file_preserving_format(input_file, links_to_update)

    print(f"\n{'='*70}")
    print(f"Total lines updated: {changes_count}")
    print(f"{'='*70}\n")

    if changes_count > 0:
        print("✓ File updated successfully!")
        print(f"✓ Backup saved to {backup_file}")
        print("\nPlease verify the changes with: git diff indication_paths.yaml")
    else:
        print("⚠ Warning: Expected to make changes but none were made.")


if __name__ == "__main__":
    main()
