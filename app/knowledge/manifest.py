import hashlib, json
from pathlib import Path
from .config import MANIFEST_FILE

def hash_file(path: Path, block_size=1024*1024):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            block = handle.read(block_size)
            if not block: break
            digest.update(block)
    return digest.hexdigest()

class KnowledgeManifest:
    def __init__(self):
        MANIFEST_FILE.parent.mkdir(parents=True, exist_ok=True)
        self.path = MANIFEST_FILE
        self.data = self._load()
    def _load(self):
        if not self.path.exists(): return {"documents": {}}
        try: return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError): return {"documents": {}}
    def save(self):
        self.path.write_text(json.dumps(self.data, indent=2, sort_keys=True), encoding="utf-8")
    def get(self, source): return self.data["documents"].get(str(source))
    def unchanged(self, source, digest):
        existing=self.get(source); return bool(existing and existing.get("sha256") == digest)
    def update(self, source, digest, chunks, metadata=None):
        self.data["documents"][str(source)]={"sha256":digest,"chunks":chunks,"metadata":metadata or {}}
    def remove(self, source): self.data["documents"].pop(str(source), None)
    def sources(self): return set(self.data["documents"].keys())
