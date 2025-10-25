import requests
import json
import time
import os
from dotenv import load_dotenv
import yake  # <-- NEW: Import the keyword extractor

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
        
        # --- NEW: Initialize the Keyword Extractor ---
        # You can tune this: n=max ngram size, top=number of keywords
        self.kw_extractor = yake.KeywordExtractor(n=3, top=5, dediplication_threshold=0.9)


    def _format_results_enriched(self, api_result: dict) -> list[dict]:
        """
        Formats the /parse API results into the target list format
        with enriched (but not generative) metadata.
        """
        final_json_list = []
        doc_id_counter = 1
        
        chunks = api_result.get("chunks", [])
        if not chunks:
            print("Warning: No chunks were returned from the parse API.")
            return []

        print("Formatting parsed segments...")

        for chunk in chunks:
            for segment in chunk.get("segments", []):
                
                text_content = segment.get("content")
                if not text_content or len(text_content.strip()) < 10:
                    continue
                
                text_content = text_content.strip()

                # --- Enriched Metadata (No GenAI) ---

                # 1. Self-Calculated Metadata
                word_count = len(text_content.split())
                kw_list = self.kw_extractor.extract_keywords(text_content)
                # Get just the keyword text, not the score
                keywords = [kw[0] for kw in kw_list]

                # 2. API-Provided Structural Metadata (with defaults)
                # We try to get these; if they don't exist, they will be None or []
                metadata = {
                    "source_segment_type": segment.get("segment_type", "Unknown"),
                    "page_number": segment.get("page_number", -1),
                    
                    # Hierarchical info (if provided by API)
                    "parent_id": segment.get("parent_id"), 
                    "category_depth": segment.get("category_depth"),
                    
                    # Formatting info (if provided by API)
                    "emphasized_text": segment.get("emphasized_text_contents", []),
                    
                    # Self-calculated info
                    "text_word_count": word_count,
                    "keywords": keywords
                }
                # --- End Enriched Metadata ---


                # Assemble the final object
                formatted_doc = {
                    "id": f"doc-{doc_id_counter}",
                    "text": text_content,
                    "metadata": metadata
                }
                
                final_json_list.append(formatted_doc)
                doc_id_counter += 1
        
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

        # === Step 3: Format the Results ===
        # Call the updated formatting function
        return self._format_results_enriched(raw_results)

# --- Example Usage ---
if __name__ == "__main__":
    
    UNSILOED_KEY = os.getenv("UNSILOED_API_KEY")
    
    if not UNSILOED_KEY:
        raise ValueError("Please set 'UNSILOED_API_KEY' in your .env file.")
            
    PDF_PATH = "Yatharth-Kapadia-Resume-ALL.pdf"
    
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