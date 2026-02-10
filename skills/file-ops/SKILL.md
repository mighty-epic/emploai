---
name: file-ops
description: Advanced file operations including batch processing, file organization, content extraction, and automated file management. Use when working with files in complex ways.
---

# File Operations Skill

This skill provides advanced file operation capabilities beyond basic read/write.

## Capabilities

### Batch Operations

Process multiple files at once:

```python
# Example: Rename all .txt files with a prefix
import os
from pathlib import Path

def batch_rename(directory, pattern, prefix):
    for file in Path(directory).glob(pattern):
        new_name = prefix + file.name
        file.rename(file.parent / new_name)
```

### File Organization

Organize files by type, date, or custom rules:

```python
# Example: Organize files by extension
from pathlib import Path
import shutil

def organize_by_type(source_dir):
    for file in Path(source_dir).iterdir():
        if file.is_file():
            ext = file.suffix.lower()
            target_dir = Path(source_dir) / ext.lstrip('.')
            target_dir.mkdir(exist_ok=True)
            shutil.move(str(file), str(target_dir / file.name))
```

### Content Extraction

Extract and process content from various file types:

- **Text files**: Direct reading
- **PDFs**: Text extraction using pdfplumber
- **Images**: OCR using pytesseract
- **Office docs**: python-docx, openpyxl
- **Archives**: zipfile, tarfile

### Search and Filter

Find files matching complex criteria:

```python
from pathlib import Path

def find_files(directory, pattern, size_limit=None, modified_after=None):
    results = []
    for file in Path(directory).rglob(pattern):
        if file.is_file():
            if size_limit and file.stat().st_size > size_limit:
                continue
            if modified_after and file.stat().st_mtime < modified_after:
                continue
            results.append(file)
    return results
```

### File Integrity

Checksums and validation:

```python
import hashlib

def calculate_checksum(filepath, algorithm='sha256'):
    hasher = hashlib.new(algorithm)
    with open(filepath, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b''):
            hasher.update(chunk)
    return hasher.hexdigest()

def verify_file(filepath, expected_hash, algorithm='sha256'):
    actual_hash = calculate_checksum(filepath, algorithm)
    return actual_hash == expected_hash
```

## Common Tasks

### Find Duplicate Files

```python
from pathlib import Path
import hashlib
from collections import defaultdict

def find_duplicates(directory):
    hashes = defaultdict(list)
    for file in Path(directory).rglob('*'):
        if file.is_file():
            file_hash = hashlib.md5(file.read_bytes()).hexdigest()
            hashes[file_hash].append(file)
    return [files for files in hashes.values() if len(files) > 1]
```

### Sync Directories

```python
import shutil
from pathlib import Path

def sync_directories(source, target, delete_extra=False):
    source_path = Path(source)
    target_path = Path(target)
    
    # Copy new/modified files
    for src_file in source_path.rglob('*'):
        if src_file.is_file():
            rel_path = src_file.relative_to(source_path)
            tgt_file = target_path / rel_path
            
            if not tgt_file.exists() or src_file.stat().st_mtime > tgt_file.stat().st_mtime:
                tgt_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_file, tgt_file)
    
    # Remove extra files from target
    if delete_extra:
        for tgt_file in target_path.rglob('*'):
            if tgt_file.is_file():
                rel_path = tgt_file.relative_to(target_path)
                src_file = source_path / rel_path
                if not src_file.exists():
                    tgt_file.unlink()
```

### Archive Operations

```python
import zipfile
import tarfile
from pathlib import Path

def create_archive(source_files, archive_path, format='zip'):
    if format == 'zip':
        with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for file in source_files:
                zf.write(file, Path(file).name)
    elif format in ('tar', 'tar.gz'):
        mode = 'w:gz' if format == 'tar.gz' else 'w'
        with tarfile.open(archive_path, mode) as tf:
            for file in source_files:
                tf.add(file, Path(file).name)

def extract_archive(archive_path, extract_to):
    if archive_path.endswith('.zip'):
        with zipfile.ZipFile(archive_path, 'r') as zf:
            zf.extractall(extract_to)
    elif archive_path.endswith(('.tar', '.tar.gz', '.tgz')):
        with tarfile.open(archive_path, 'r') as tf:
            tf.extractall(extract_to)
```

### Watch for File Changes

```python
import time
from pathlib import Path

def watch_directory(directory, callback, interval=1):
    path = Path(directory)
    last_state = {f: f.stat().st_mtime for f in path.rglob('*') if f.is_file()}
    
    while True:
        time.sleep(interval)
        current_state = {f: f.stat().st_mtime for f in path.rglob('*') if f.is_file()}
        
        # Check for new files
        for f, mtime in current_state.items():
            if f not in last_state:
                callback('created', f)
            elif last_state[f] != mtime:
                callback('modified', f)
        
        # Check for deleted files
        for f in last_state:
            if f not in current_state:
                callback('deleted', f)
        
        last_state = current_state
```

## Error Handling

Always handle common file operation errors:

```python
from pathlib import Path
import errno

def safe_file_operation(filepath, operation):
    try:
        return operation(filepath)
    except FileNotFoundError:
        return f"Error: File not found - {filepath}"
    except PermissionError:
        return f"Error: Permission denied - {filepath}"
    except IsADirectoryError:
        return f"Error: Path is a directory - {filepath}"
    except OSError as e:
        if e.errno == errno.ENOSPC:
            return f"Error: Disk full"
        return f"Error: {e}"
```

## Performance Tips

1. **Use pathlib over os.path**: More intuitive and powerful
2. **Process in chunks**: For large files, read/write in chunks
3. **Use glob patterns**: For filtering files efficiently
4. **Batch operations**: Group operations to minimize disk I/O
5. **Cache metadata**: Store file stats to avoid repeated stat calls

## Security Considerations

- Always validate file paths (prevent directory traversal)
- Check file permissions before operations
- Use temporary files for atomic operations
- Verify checksums for critical files
- Be careful with recursive operations
- Handle symlinks appropriately
