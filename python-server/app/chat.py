import sys

from llama_stack_client import LlamaStackClient

SERVER_URL = "http://localhost:8321"
MODEL_ID = "llama3.2:3b"
SYSTEM_PROMPT = "You are a helpful assistant."
VECTOR_DB_ID = "tutorial_db"

def main():
    with LlamaStackClient(base_url=SERVER_URL) as client:

        # Connectivity check and model availability
        try:
            models = [m.identifier for m in client.models.list()]
            if MODEL_ID not in models:
                print(f"Warning: '{MODEL_ID}' not found. Available: {models}", file=sys.stderr)
        except Exception as e:
            print(f"Cannot reach server at {SERVER_URL}: {e}", file=sys.stderr)
            return

        print(f"Connected to {SERVER_URL} | Model: {MODEL_ID}")

        conversation = [{"role": "system", "content": SYSTEM_PROMPT}]

        while True:
            try:
                user_input = input("You: ").strip()
            except (KeyboardInterrupt, EOFError):
                print("\nExiting.")
                break

            if not user_input:
                continue
            if user_input.lower() in ("quit", "exit"):
                break

            conversation.append({"role": "user", "content": user_input})

            try:
                stream = client.inference.chat_completion(
                    model_id=MODEL_ID,
                    messages=conversation,
                    stream=True,
                )

                print("Assistant: ", end="", flush=True)

                reply = ""
                for chunk in stream:
                    delta = chunk.event.delta
                    if hasattr(delta, "text") and delta.text:
                        print(delta.text, end="", flush=True)
                        reply += delta.text
                print()
                conversation.append({"role": "assistant", "content":
    reply})

            except Exception as e:
                print(f"\n[Error] {e}", file=sys.stderr)
                break


if __name__ == "__main__":
    main()