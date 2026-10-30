"""Bounded file operations shared by publication, verification and downloads."""
import hashlib


def digest_file(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
