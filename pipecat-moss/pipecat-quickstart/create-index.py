import asyncio
import os

from dotenv import load_dotenv
from inferedge_moss import DocumentInfo, MossClient
from loguru import logger

load_dotenv()


async def upload_documents():
    """Upload documents to the Moss index.

    This function creates an index in the Moss service with the provided documents.
    """
    logger.debug("Starting the document upload process...")

    client = MossClient(
        project_id=os.getenv("MOSS_PROJECT_ID"), project_key=os.getenv("MOSS_PROJECT_KEY")
    )

    # Create documents
    documents = [
        DocumentInfo(
            id="doc-1",
            text="How do I track my order? You can track your order by logging into your account and visiting the 'Order History' section. Each order has a unique tracking number that you can use to monitor its delivery status.",
            metadata={"category": "orders", "topic": "tracking", "difficulty": "beginner"},
        ),
        DocumentInfo(
            id="doc-2",
            text="What is your return policy? We offer a 30-day return policy for most items. Products must be unused and in their original packaging. Return shipping costs may apply unless the item is defective.",
            metadata={"category": "returns", "topic": "policy", "difficulty": "beginner"},
        ),
        DocumentInfo(
            id="doc-3",
            text="How can I change my shipping address? You can change your shipping address before order dispatch by contacting our customer service team. Once an order is dispatched, the shipping address cannot be modified.",
            metadata={"category": "shipping", "topic": "address_change", "difficulty": "beginner"},
        ),
        DocumentInfo(
            id="doc-4",
            text="Do you ship internationally? Yes, we ship to most countries worldwide. International shipping costs and delivery times vary by location. You can check shipping rates during checkout.",
            metadata={"category": "shipping", "topic": "international", "difficulty": "beginner"},
        ),
        DocumentInfo(
            id="doc-5",
            text="How do I reset my password? Click the 'Forgot Password' link on the login page. Enter your email address, and we'll send you instructions to reset your password.",
            metadata={"category": "account", "topic": "password_reset", "difficulty": "beginner"},
        ),
        DocumentInfo(
            id="doc-6",
            text="What payment methods do you accept? We accept Visa, Mastercard, American Express, PayPal, and Apple Pay. All payments are processed securely through our encrypted payment system.",
            metadata={"category": "payment", "topic": "methods", "difficulty": "beginner"},
        ),
        DocumentInfo(
            id="doc-7",
            text="How long does shipping take? Standard domestic shipping typically takes 3-5 business days. Express shipping (1-2 business days) is available for most locations at an additional cost.",
            metadata={"category": "shipping", "topic": "delivery_time", "difficulty": "beginner"},
        ),
        DocumentInfo(
            id="doc-8",
            text="Can I cancel my order? Orders can be cancelled within 1 hour of placement. After that, if the order has not been shipped, you may contact customer service to request cancellation.",
            metadata={"category": "orders", "topic": "cancellation", "difficulty": "beginner"},
        ),
        DocumentInfo(
            id="doc-9",
            text="Do you offer gift wrapping? Yes, gift wrapping is available for most items at checkout for a small additional fee. You can also include a personalized gift message.",
            metadata={"category": "services", "topic": "gift_wrapping", "difficulty": "beginner"},
        ),
        DocumentInfo(
            id="doc-10",
            text="What is your price match policy? We match prices from authorized retailers for identical items within 14 days of purchase. Send us proof of the lower price, and we'll refund the difference.",
            metadata={"category": "pricing", "topic": "price_match", "difficulty": "intermediate"},
        ),
    ]

    try:
        logger.debug("Creating the index...")
        await client.create_index(
            index_name=os.getenv("MOSS_INDEX_NAME"),
            docs=documents,
            model_id="moss-minilm",
        )
        logger.success("Index created successfully.")

    except Exception as e:
        logger.error("An error occurred: {0}", str(e))
        raise


# Run the async function
if __name__ == "__main__":
    asyncio.run(upload_documents())
