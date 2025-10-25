import requests
import json
import time
import os
from dotenv import load_dotenv
import yake  # <-- Import the keyword extractor
import re
from typing import List
from settings import get_settings

# Load API keys from .env file
load_dotenv()

class PdfChunker:
    """
    A class to process a PDF file using ONLY the unsiloed.ai /parse
    endpoint. It chunks the document and enriches the metadata with
    structural info from the API and calculated info (keywords, length).
    
    This script does NOT require a generative AI.
    """

    def __init__(self, unsiloed_api_key: str):
        """
        Initializes the converter with the Unsiloed API key.
        """
        if not unsiloed_api_key or unsiloed_api_key == "YOUR_API_KEY_HERE":
            raise ValueError("Uniloed API key is not set.")
            
        self.unsiloed_base_url = "https://prod.visionapi.unsiloed.ai"
        self.unsiloed_headers = {
            "accept": "application/json",
            "api-key": unsiloed_api_key
        }
        
        # --- Initialize the Keyword Extractor ---
        # You can tune this: n=max ngram size, top=number of keywords
        self.kw_extractor = yake.KeywordExtractor(n=3, top=5, dedupLim=0.9)
        
        # Get settings for token limits
        self.settings = get_settings()
        self.max_tokens_per_chunk = self.settings.unslolied.max_tokens_per_chunk
        self.overlap_tokens = self.settings.unslolied.overlap_tokens

    def _count_tokens(self, text: str) -> int:
        """
        Simple token counting function.
        This is a rough approximation - for production, consider using tiktoken or similar.
        """
        # Split by whitespace and punctuation, then count
        tokens = re.findall(r'\b\w+\b|[^\w\s]', text)
        return len(tokens)

    def _create_overlapping_chunks(self, text: str, max_tokens: int, overlap_tokens: int) -> List[str]:
        """
        Create overlapping chunks from text based on token limits.
        """
        if not text.strip():
            return []
        
        # Split text into words for token-based chunking
        words = text.split()
        chunks = []
        
        if len(words) <= max_tokens:
            return [text]
        
        start_idx = 0
        while start_idx < len(words):
            # Calculate end index for this chunk
            end_idx = min(start_idx + max_tokens, len(words))
            
            # Create chunk
            chunk_words = words[start_idx:end_idx]
            chunk_text = ' '.join(chunk_words)
            chunks.append(chunk_text)
            
            # Move start index for next chunk with overlap
            if end_idx >= len(words):
                break
            start_idx = end_idx - overlap_tokens
            
            # Ensure we don't go backwards
            if start_idx <= 0:
                start_idx = end_idx
        
        return chunks

    def _format_results_enriched(self, api_result: dict) -> list[dict]:
        """
        Formats the /parse API results into the target list format
        with enriched metadata, creating one index per chunk.
        
        CORRECT IMPLEMENTATION:
        1. Each chunk becomes one index
        2. Concatenate all OCR items from all segments within each chunk
        3. Check if concatenated content exceeds token limit
        4. If exceeds: Split the concatenated text and create multiple indices
        5. If within limit: Create single index
        """
        final_json_list = []
        doc_id_counter = 1
        
        chunks = api_result.get("chunks", [])
        if not chunks:
            print("Warning: No chunks were returned from the parse API.")
            return []

        print(f"Processing {len(chunks)} chunks with OCR item concatenation...")

        # Process each chunk individually
        for chunk_idx, chunk in enumerate(chunks):
            print(f"Processing chunk {chunk_idx + 1}/{len(chunks)}")
            
            # Collect all OCR text from all segments in this chunk
            chunk_texts = []
            total_ocr_items = 0
            segment_types = []
            page_numbers = []
            
            for segment in chunk.get("segments", []):
                # Get OCR items from the segment
                ocr_items = segment.get("ocr", [])
                if not ocr_items:
                    # Fallback to content if no OCR items
                    text_content = segment.get("content", "")
                    if not text_content or len(text_content.strip()) < 10:
                        continue
                    segment_text = text_content.strip()
                else:
                    # Concatenate all OCR items text
                    ocr_texts = [item.get("text", "") for item in ocr_items if item.get("text")]
                    if not ocr_texts:
                        continue
                    segment_text = " ".join(ocr_texts).strip()
                
                if len(segment_text) < 10:
                    continue
                
                chunk_texts.append(segment_text)
                total_ocr_items += len(ocr_items)
                segment_types.append(segment.get("segment_type", "Unknown"))
                page_numbers.append(segment.get("page_number", -1))
            
            if not chunk_texts:
                print(f"  No valid content found in chunk {chunk_idx + 1}, creating empty index")
                # Create an empty index for chunks with no content
                chunk_id = f"doc-{doc_id_counter}"
                doc_id_counter += 1
                
                metadata = {
                    "source_chunk_index": str(chunk_idx + 1),
                    "segments_count": "0",
                    "segment_types": "Empty",
                    "page_number": "Unknown",
                    "ocr_items_count": "0",
                    "chunk_index": "1",
                    "total_chunks": "1",
                    "token_count": "0",
                    "keywords": ""
                }
                
                formatted_doc = {
                    "id": chunk_id,
                    "text": "",
                    "metadata": metadata
                }
                
                final_json_list.append(formatted_doc)
                continue
            
            # Concatenate all segment texts in this chunk
            concatenated_chunk_text = " ".join(chunk_texts)
            token_count = self._count_tokens(concatenated_chunk_text)
            
            print(f"  Chunk contains {len(chunk_texts)} segments, {total_ocr_items} OCR items, {token_count} tokens")
            
            if token_count <= self.max_tokens_per_chunk:
                # Chunk fits within token limit, create single index
                chunks_for_chunk = [concatenated_chunk_text]
                print(f"  Chunk fits within limit ({token_count} tokens)")
            else:
                # Chunk exceeds token limit, split it
                print(f"  Chunk exceeds token limit ({token_count} > {self.max_tokens_per_chunk}). Splitting...")
                chunks_for_chunk = self._create_overlapping_chunks(
                    concatenated_chunk_text, 
                    self.max_tokens_per_chunk, 
                    self.overlap_tokens
                )
                print(f"  Split into {len(chunks_for_chunk)} sub-chunks")
            
            # Create final documents for each chunk/sub-chunk with UNIQUE IDs
            for i, chunk_text in enumerate(chunks_for_chunk):
                # Create a UNIQUE ID for each index
                unique_id = f"doc-{doc_id_counter}"
                doc_id_counter += 1
                # Extract keywords from this chunk
                kw_list = self.kw_extractor.extract_keywords(chunk_text)
                keywords_list = [kw[0] for kw in kw_list]
                keywords_str = ", ".join(keywords_list)
                
                # Get page range for metadata
                valid_pages = [p for p in page_numbers if p != -1]
                page_range = f"{min(valid_pages)}-{max(valid_pages)}" if valid_pages else "Unknown"
                
                # Create metadata
                metadata = {
                    "source_chunk_index": str(chunk_idx + 1),
                    "segments_count": str(len(chunk_texts)),
                    "segment_types": ", ".join(set(segment_types)),
                    "page_number": page_range,
                    "ocr_items_count": str(total_ocr_items),
                    "chunk_index": str(i + 1),
                    "total_chunks": str(len(chunks_for_chunk)),
                    "token_count": str(self._count_tokens(chunk_text)),
                    "keywords": keywords_str
                }
                
                # Create the final document with a UNIQUE ID
                formatted_doc = {
                    "id": unique_id,
                    "text": chunk_text,
                    "metadata": metadata
                }
                
                final_json_list.append(formatted_doc)
        
        print(f"Created {len(final_json_list)} total documents from {len(chunks)} original chunks")
        return final_json_list

    def process_pdf(self, pdf_file_path: str, poll_interval: int = 5) -> list[dict]:
        """
        Processes a PDF file and returns the chunked data.
        (This function is unchanged)
        """
        
        if not os.path.exists(pdf_file_path):
            raise FileNotFoundError(f"No file found at {pdf_file_path}")

        # === Step 1: Submit Job to /parse endpoint ===
        print(f"Submitting parse job for {pdf_file_path}...")
        
        data = {
            "segmentation_method": "Smart Layout Detection",
            "OCR_Mode": "Process All Content",
            "ocr_engine": "UnsiloedHawk"
        }
        
        with open(pdf_file_path, "rb") as f:
            files = {"file": (os.path.basename(pdf_file_path), f, "application/pdf")}
            
            try:
                response = requests.post(
                    f"{self.unsiloed_base_url}/parse",
                    headers=self.unsiloed_headers,
                    files=files,
                    data=data
                )
                response.raise_for_status()
            except requests.exceptions.HTTPError as e:
                print(f"HTTP Error submitting job: {e.response.text}")
                raise
        
        job_info = response.json()
        job_id = job_info.get("job_id")
        if not job_id:
            raise Exception(f"Failed to create parse job: {job_info.get('message')}")
        
        print(f"Job created successfully: {job_id}")
        print(f"Quota remaining: {job_info.get('quota_remaining')}")

        # === Step 2: Poll for Completion ===
        status_url = f"{self.unsiloed_base_url}/parse/{job_id}"
        print("Polling for job completion...")
        
        raw_results = {}
        while True:
            try:
                status_response = requests.get(status_url, headers=self.unsiloed_headers)
                status_response.raise_for_status()
                
                status_data = status_response.json()
                status = status_data.get("status")

                if status == "Succeeded":
                    print("Parse job completed successfully.")
                    raw_results = status_data
                    break
                elif status == "Failed":
                    raise Exception(f"Job failed: {status_data.get('message', 'Unknown error')}")
                else:
                    print(f"Job status: {status}. Waiting {poll_interval}s...")
                    time.sleep(poll_interval)

            except requests.exceptions.HTTPError as e:
                print(f"HTTP Error checking status: {e.response.text}")
                raise

        # === Step 3: Save Raw Results and Format the Results ===
        # Save JSON Raw Results before enriching
        raw_json_filename = "raw_parse_results.json"
        with open(raw_json_filename, 'w', encoding='utf-8') as f:
            json.dump(raw_results, f, indent=2)
        print(f"Raw JSON results saved to {raw_json_filename}")

        # Call the updated formatting function and return enriched results
        return self._format_results_enriched(raw_results)

# --- Example Usage ---
if __name__ == "__main__":
    from settings import get_settings
    settings = get_settings()
    
    UNSILOED_KEY = os.getenv("UNSILOED_API_KEY")
    
    if not UNSILOED_KEY:
        raise ValueError("Please set 'UNSILOED_API_KEY' in your .env file.")
            
    PDF_PATH = settings.unslolied.data_path
    
    if not os.path.exists(PDF_PATH):
        print(f"Error: The file '{PDF_PATH}' was not found.")
    else:
        try:
            converter = PdfChunker(unsiloed_api_key=UNSILOED_KEY)
            json_data = converter.process_pdf(PDF_PATH)
            
            print("\n--- Formatted JSON Output (Enriched) ---")
            print(json.dumps(json_data, indent=2))
            
            output_filename = f"{os.path.splitext(PDF_PATH)[0]}_parsed.json"
            with open(output_filename, 'w') as f:
                json.dump(json_data, f, indent=2)
            print(f"\nResults also saved to {output_filename}")

        except Exception as e:
            print(f"An unexpected error occurred: {e}")