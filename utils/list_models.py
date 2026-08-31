import os
import google.generativeai as genai


def main():
    # Configure API key (must be in environment)
    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

    print("Available Gemini Models:")
    for model in genai.list_models():
        print(" -", model.name)


if __name__ == "__main__":
    main()