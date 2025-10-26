"""Utility script to create or refresh the Moss FAQ index.

Processes PDF documents using Unsiloed API and uploads them to the Moss service
using credentials defined in ``.env``.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import List

from dotenv import load_dotenv
from inferedge_moss import DocumentInfo, MossClient

from settings import get_settings
from tool import PdfChunker

# Load environment variables from the project .env file
load_dotenv(".env")

# Get configuration settings
settings = get_settings()

PDF_PATH = Path(__file__).resolve().parent / settings.unsiloed.data_path


def _load_documents() -> List[DocumentInfo]:
    """Load documents by processing PDF file using Unsiloed API."""
    if not PDF_PATH.exists():
        raise FileNotFoundError(
            f"PDF file not found at {PDF_PATH}. Please ensure the PDF file exists."
        )

    # Get Unsiloed API key from environment
    unsiloed_api_key = os.getenv("UNSILOED_API_KEY")
    if not unsiloed_api_key:
        raise ValueError("UNSILOED_API_KEY environment variable is not set.")

    print(f"Processing PDF file: {PDF_PATH}")
    print("This may take a few minutes depending on the PDF size...")
    
    try:
        # Initialize PDF processor
        pdf_processor = PdfChunker(unsiloed_api_key=unsiloed_api_key)
        
        # Process the PDF and get chunked documents
        pdf_documents = pdf_processor.process_pdf(str(PDF_PATH))
        
        print(f"Successfully processed PDF into {len(pdf_documents)} document chunks")
        
        # Convert to DocumentInfo objects for Moss
        documents: List[DocumentInfo] = []
        for doc in pdf_documents:
            if not isinstance(doc, dict):
                continue
                
            doc_id = doc.get("id")
            text = doc.get("text")
            if not doc_id or not text:
                continue
                
            metadata = doc.get("metadata")
            if metadata is not None and not isinstance(metadata, dict):
                metadata = None

            documents.append(
                DocumentInfo(
                    id=str(doc_id),
                    text=str(text),
                    metadata=metadata or {},
                )
            )

        if not documents:
            raise ValueError("No valid documents were generated from the PDF file.")

        print(f"Created {len(documents)} documents for Moss index")
        return documents
        
    except Exception as e:
        raise Exception(f"Failed to process PDF file: {str(e)}")


async def create_pdf_index() -> None:
    """Create Moss index from PDF documents processed via Unsiloed API."""
    moss_config = settings.moss
    documents = _load_documents()

    client = MossClient(
        os.environ["MOSS_PROJECT_ID"],
        os.environ["MOSS_PROJECT_KEY"]
    )

    print(
        f"Creating Moss index '{moss_config.index_name}' with {len(documents)} "
        f"PDF document chunks using {moss_config.model_id}..."
    )
    created = await client.create_index(
        moss_config.index_name,
        documents,
        moss_config.model_id
    )
    print("Index creation response:", created)
    print("PDF document index ready for use!")


if __name__ == "__main__":
    asyncio.run(create_pdf_index())
