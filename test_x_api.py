import os
import tweepy
from dotenv import load_dotenv

load_dotenv()

def test_x_api():
    try:
        client = tweepy.Client(
            bearer_token=os.getenv("X_BEARER_TOKEN"),
            consumer_key=os.getenv("X_CONSUMER_KEY"),
            consumer_secret=os.getenv("X_CONSUMER_SECRET"),
            access_token=os.getenv("X_ACCESS_TOKEN"),
            access_token_secret=os.getenv("X_ACCESS_SECRET")
        )
        
        response = client.create_tweet(text="Hello world! This is a test tweet from my hot deal bot. 🤖")
        print(f"✅ Success! Tweet ID: {response.data['id']}")
    except Exception as e:
        print(f"❌ Failed: {e}")

if __name__ == "__main__":
    test_x_api()
