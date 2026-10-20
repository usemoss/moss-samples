"""
Build a `moss-litelm` index in the cloud for on-device search.

The cloud embeds the documents with `moss-litelm` and stores a compact INT8
index. An app then loads that index with the same project credentials and
queries it on-device with `moss-litelm`, without embedding the documents again.

Prerequisites:
  - Python SDK `moss`.
  - The project's organization has access to `moss-litelm`.
  - MOSS_PROJECT_ID / MOSS_PROJECT_KEY in the environment (or samples/.env).

Run:
  python samples/ios_cloud_index.py
"""
import asyncio
import os
import time

from dotenv import load_dotenv
from moss import DocumentInfo, MossClient

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

INDEX_NAME = os.getenv("MOSS_INDEX", "video-scenes")
MODEL_ID = "moss-litelm"  # the model the app queries with on-device

# Representative records, one document per scene, with metadata for
# filtered queries on-device (for example, a single video).
SCENES = [
    DocumentInfo(id="v1#0", text="A cyclist rides along a coastal road at sunset.",
                 metadata={"video_id": "v1", "scene": "0", "t_start": "0"}),
    DocumentInfo(id="v1#1", text="Two people unload boxes from a delivery van.",
                 metadata={"video_id": "v1", "scene": "1", "t_start": "42"}),
    DocumentInfo(id="v2#0", text="A chef plates a dessert in a busy restaurant kitchen.",
                 metadata={"video_id": "v2", "scene": "0", "t_start": "0"}),
    DocumentInfo(id="v2#1", text="Customers wait in line at the counter to pay.",
                 metadata={"video_id": "v2", "scene": "1", "t_start": "75"}),
]


async def main() -> None:
    pid, key = os.getenv("MOSS_PROJECT_ID"), os.getenv("MOSS_PROJECT_KEY")
    if not pid or not key:
        print("Set MOSS_PROJECT_ID / MOSS_PROJECT_KEY (see samples/.env)")
        return

    client = MossClient(pid, key)

    print(f"Creating cloud index '{INDEX_NAME}' with {MODEL_ID} ({len(SCENES)} docs)...")
    result = await client.create_index(INDEX_NAME, SCENES, model_id=MODEL_ID)

    # The build runs in the background: the cloud embeds, then builds the index.
    start = time.perf_counter()
    while True:
        st = await client.get_job_status(result.job_id)
        status = st.status.value
        if status in ("completed", "failed"):
            break
        if time.perf_counter() - start > 180:
            raise TimeoutError(f"job {result.job_id} stuck in {status}")
        await asyncio.sleep(2)

    if status != "completed":
        raise RuntimeError(f"index build failed: {getattr(st, 'error', None)}")

    info = await client.get_index(INDEX_NAME)
    print(f"'{INDEX_NAME}' ready: {info.doc_count} docs, model={info.model.id}")
    print("Load it in an app with the same project credentials,")
    print("then query it on-device (MossClient.loadIndex, then query).")


if __name__ == "__main__":
    asyncio.run(main())
