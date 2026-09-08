from pathlib import Path
from uuid import uuid5, NAMESPACE_URL

from qdrant_client import QdrantClient, models

from .chunking import chunk_text
from .config import (
    COLLECTION_NAME,
    DEFAULT_TOP_K,
    EMBEDDING_MODEL,
    KNOWLEDGE_DIR,
    VECTORSTORE_DIR,
    CHUNK_SIZE,
    CHUNK_OVERLAP,
    SUPPORTED_EXTENSIONS,
)
from .loaders import load_document
from .manifest import KnowledgeManifest, hash_file
from .hybrid import rerank


class KnowledgeEngine:
    """Persistent ICT knowledge engine with incident-aware Markdown ingestion."""

    def __init__(self):
        KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
        VECTORSTORE_DIR.mkdir(parents=True, exist_ok=True)

        self.client = QdrantClient(path=str(VECTORSTORE_DIR))
        self.collection_name = COLLECTION_NAME
        self.embedding_model = EMBEDDING_MODEL
        self.manifest = KnowledgeManifest()

    def close(self):
        if self.client is not None:
            self.client.close()

    def _ensure_collection(self):
        if self.client.collection_exists(self.collection_name):
            return

        vector_size = self.client.get_embedding_size(
            self.embedding_model
        )

        self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config=models.VectorParams(
                size=vector_size,
                distance=models.Distance.COSINE,
            ),
        )

    def discover_documents(self):
        documents = []

        for path in KNOWLEDGE_DIR.rglob("*"):
            if (
                path.is_file()
                and path.suffix.lower() in SUPPORTED_EXTENSIONS
                and not path.name.endswith(".meta.json")
            ):
                documents.append(path)

        return sorted(documents)

    def _delete_source_points(self, source: str):
        if not self.client.collection_exists(
            self.collection_name
        ):
            return

        self.client.delete(
            collection_name=self.collection_name,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="source",
                            match=models.MatchValue(value=source),
                        )
                    ]
                )
            ),
            wait=True,
        )

    def ingest_file(self, path: Path, force=False):
        path = Path(path).resolve()
        digest = hash_file(path)

        if (
            not force
            and self.manifest.unchanged(
                str(path),
                digest,
            )
        ):
            existing = self.manifest.get(str(path))

            return {
                "source": str(path),
                "status": "unchanged",
                "chunks": existing.get("chunks", 0),
            }

        document = load_document(path)
        metadata = document["metadata"]

        chunk_records = []

        for section in document["sections"]:
            page = section.get("page")
            heading = section.get("heading")
            heading_level = section.get("heading_level")
            incident_part = section.get("incident_part")
            pre_chunked = section.get("pre_chunked", False)

            if pre_chunked:
                chunks = [section["text"]]
            else:
                chunks = chunk_text(
                    section["text"],
                    chunk_size=CHUNK_SIZE,
                    overlap=CHUNK_OVERLAP,
                )

            for local_index, chunk in enumerate(chunks, start=1):
                chunk_records.append({
                    "text": chunk,
                    "page": page,
                    "heading": heading,
                    "heading_level": heading_level,
                    "incident_part": (
                        incident_part
                        if incident_part is not None
                        else local_index
                    ),
                })

        if not chunk_records:
            return {
                "source": str(path),
                "status": "empty",
                "chunks": 0,
            }

        self._ensure_collection()
        self._delete_source_points(str(path))

        ids = []
        vectors = []
        payloads = []

        for index, record in enumerate(chunk_records):
            point_id = str(
                uuid5(
                    NAMESPACE_URL,
                    (
                        f"{path}::{digest}::{index}::"
                        f"{record['page']}::{record['heading']}::"
                        f"{record['incident_part']}"
                    ),
                )
            )

            payload = {
                **metadata,
                "chunk_index": index,
                "page": record["page"],
                "heading": record["heading"],
                "heading_level": record["heading_level"],
                "incident_part": record["incident_part"],
                "text": record["text"],
                "sha256": digest,
            }

            ids.append(point_id)
            vectors.append(
                models.Document(
                    text=record["text"],
                    model=self.embedding_model,
                )
            )
            payloads.append(payload)

        self.client.upload_collection(
            collection_name=self.collection_name,
            vectors=vectors,
            payload=payloads,
            ids=ids,
            wait=True,
        )

        self.manifest.update(
            source=str(path),
            digest=digest,
            chunks=len(chunk_records),
            metadata=metadata,
        )
        self.manifest.save()

        return {
            "source": str(path),
            "status": "indexed",
            "chunks": len(chunk_records),
        }

    def remove_deleted_sources(self):
        current = {
            str(path.resolve())
            for path in self.discover_documents()
        }

        removed = []

        for source in self.manifest.sources() - current:
            self._delete_source_points(source)
            self.manifest.remove(source)
            removed.append(source)

        if removed:
            self.manifest.save()

        return removed

    def ingest_all(self, force=False):
        results = []

        for document in self.discover_documents():
            results.append(
                self.ingest_file(
                    document,
                    force=force,
                )
            )

        removed = self.remove_deleted_sources()

        return {
            "documents": results,
            "removed": removed,
        }

    def search(
        self,
        query: str,
        top_k: int = DEFAULT_TOP_K,
        category: str | None = None,
    ):
        if not isinstance(query, str):
            raise ValueError("query must be a string")

        query = query.strip()

        if not query:
            raise ValueError("query must not be empty")

        if not self.client.collection_exists(
            self.collection_name
        ):
            return []

        top_k = max(1, min(int(top_k), 20))
        semantic_limit = max(top_k, min(top_k * 4, 40))

        query_filter = None

        if category:
            query_filter = models.Filter(
                must=[
                    models.FieldCondition(
                        key="category",
                        match=models.MatchValue(value=category),
                    )
                ]
            )

        response = self.client.query_points(
            collection_name=self.collection_name,
            query=models.Document(
                text=query,
                model=self.embedding_model,
            ),
            query_filter=query_filter,
            limit=semantic_limit,
            with_payload=True,
        )

        candidates = []

        for point in response.points:
            payload = point.payload or {}

            citation = {
                "title": payload.get("title"),
                "source": payload.get("source"),
                "filename": payload.get("filename"),
                "page": payload.get("page"),
                "heading": payload.get("heading"),
                "vendor": payload.get("vendor"),
                "product": payload.get("product"),
                "version": payload.get("version"),
                "url": payload.get("url"),
                "category": payload.get("category"),
                "knowledge_type": payload.get("knowledge_type"),
                "scope": payload.get("scope"),
                "confidence": payload.get("confidence"),
                "knowledge_status": payload.get("knowledge_status"),
                "confidence_score": payload.get("confidence_score"),
                "confirmations": payload.get("confirmations"),
                "contradictions": payload.get("contradictions"),
                "last_confirmed": payload.get("last_confirmed"),
                "stale_days": payload.get("stale_days"),
                "tags": payload.get("tags", []),
            }

            candidates.append({
                "semantic_score": round(
                    float(point.score),
                    4,
                ),
                "text": payload.get("text", ""),
                "citation": citation,
            })

        ranked = rerank(
            query,
            candidates,
        )

        return ranked[:top_k]

    def collection_count(self):
        if not self.client.collection_exists(
            self.collection_name
        ):
            return 0

        info = self.client.get_collection(
            self.collection_name
        )

        return int(
            info.points_count or 0
        )
