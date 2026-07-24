import os
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, OperationFailure

# Load environment variables from the .env file
load_dotenv()

# Fetch the variables
MONGO_URI = os.getenv("MONGO_CONNECTION_STRING")
DB_NAME = os.getenv("MONGO_DB_NAME")
COLLECTION_NAME = os.getenv("MONGO_COLLECTION_NAME")

def test_mongodb():
    if not MONGO_URI:
        print("❌ Error: MONGO_CONNECTION_STRING is missing. Check your .env file.")
        return

    print("⏳ Attempting to connect to MongoDB Atlas...")

    try:
        # 1. Connect to the cluster
        client = MongoClient(MONGO_URI)
        
        # 2. Send a 'ping' command to verify the connection is alive
        client.admin.command('ping')
        print("✅ SUCCESS: Connected to MongoDB Atlas cluster!\n")

        # 3. Access the database and collection
        db = client[DB_NAME]
        collection = db[COLLECTION_NAME]

        # 4. Insert a test document (This triggers the lazy creation!)
        print(f"⏳ Inserting test document into '{DB_NAME}.{COLLECTION_NAME}'...")
        test_doc = {"test_message": "Hello from Python!", "status": "success"}
        result = collection.insert_one(test_doc)
        print(f"✅ SUCCESS: Document inserted with ID: {result.inserted_id}\n")

        # 5. Read it back
        print("⏳ Fetching the document back...")
        fetched_doc = collection.find_one({"_id": result.inserted_id})
        print(f"✅ SUCCESS: Retrieved document: {fetched_doc}\n")

        # 6. (Optional) Clean up / Delete the test document
        collection.delete_one({"_id": result.inserted_id})
        print("🧹 Cleaned up test document.")

    except ConnectionFailure as e:
        print("❌ FAILED: Could not connect to the database.")
        print("Check if your IP address is whitelisted in Atlas (Network Access -> Add 0.0.0.0/0)")
        print(f"Error details: {e}")
    except OperationFailure as e:
        print("❌ FAILED: Authentication failed.")
        print("Check your username and password in the connection string.")
        print(f"Error details: {e}")
    except Exception as e:
        print(f"❌ An unexpected error occurred: {e}")
    finally:
        # Always close the connection when done
        if 'client' in locals():
            client.close()
            print("\n🔌 Connection closed.")

if __name__ == "__main__":
    test_mongodb()