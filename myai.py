from flask import Blueprint, render_template, request, jsonify
import os
import requests
from dotenv import load_dotenv
from google import genai

load_dotenv()
myai = Blueprint("myai", __name__)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

print("MyAI API key loaded:", bool(GEMINI_API_KEY))

SEARXNG_URL = os.environ.get(
    "SEARXNG_URL",
    "http://localhost:8080"
)

if GEMINI_API_KEY:
    gemini_client = genai.Client(
        api_key=GEMINI_API_KEY
    )
else:
    gemini_client = None


AI_MODELS = [
    "gemini-3.5-flash-lite",
    "gemini-3.8-flash",
    "gemini-3.6-flash",
    "gemini-3.7-flash"
]

def ai_web_search(query):
    try:
        response = requests.get(
            f"{SEARXNG_URL}/search",
            params={
                "q": query,
                "format": "json",
                "categories": "general"
            },
            timeout=10
        )

        response.raise_for_status()

        data = response.json()

        results = []

        for result in data.get("results", [])[:8]:
            title = result.get("title", "")
            content = result.get("content", "")
            url = result.get("url", "")

            if title and url:
                results.append({
                    "title": title,
                    "content": content,
                    "url": url
                })

        return results

    except Exception as e:
        print("MyAI search error:", e)
        return []


@myai.route("/ai")
def ai_page():
    return render_template("ai.html")


@myai.route("/api/ai", methods=["POST"])
def ai_chat():

    if not gemini_client:
        return jsonify({
            "error": "MyAI is not configured. Add GEMINI_API_KEY."
        }), 500

    data = request.get_json(silent=True) or {}

    message = data.get("message", "").strip()

    if not message:
        return jsonify({
            "error": "Please enter a message."
        }), 400

    conversation = data.get(
        "conversation",
        ""
    )

    results = ai_web_search(message)

    search_context_parts = []

    for result in results:
        search_context_parts.append(
            f"Title: {result['title']}\n"
            f"Content: {result['content']}\n"
            f"URL: {result['url']}"
        )

    search_context = "\n\n".join(
        search_context_parts
    )

    prompt = f"""
You are MyAI, the AI assistant built into MySpace.

You are helpful, honest, and clear.

SAFETY RULES:

- Do not help steal passwords, accounts, money, or personal information.
- Do not provide malware, ransomware, spyware, or credential-stealing code.
- Do not help bypass security systems without authorization.
- For cybersecurity questions, focus on defensive and authorized security.
- Do not provide instructions for seriously harming someone.
- If a request is unsafe, briefly explain that you cannot help with it.

INTERNET SEARCH RESULTS:

{search_context}

CONVERSATION:

{conversation}

CURRENT USER MESSAGE:

{message}

ANSWER RULES:

- Answer the user clearly and directly.
- Use the internet search results when they are relevant.
- Do not invent facts or URLs.
- If you use information from an internet search result, use the actual URL provided in that result when appropriate.
- When giving the user a website, article, page, video, or other online resource, make it a clickable Markdown link.
- Use this exact format:
  [Website Name](URL)
- Always use the actual URL from the search results.
- Never make up a URL.
- If the user specifically asks for a link, provide the relevant clickable link.
- If multiple useful sources are available, you may provide multiple clickable links.
"""

    last_error = None

    for model in AI_MODELS:

        print(f"MyAI trying model: {model}")

        try:

            response = gemini_client.models.generate_content(
                model=model,
                contents=prompt
            )

            answer = response.text

            print(
                f"MyAI succeeded with model: {model}"
            )

            return jsonify({
                "answer": answer,
                "sources": results,
                "model": model
            })

        except Exception as e:

            error_text = str(e)

            print(
                f"MyAI model {model} failed: "
                f"{error_text}"
            )

            last_error = e

            if (
                "429" in error_text
                or "RESOURCE_EXHAUSTED" in error_text
            ):
                print(
                    f"MyAI quota reached for {model}. "
                    "Trying next model."
                )
                continue

            if (
                "503" in error_text
                or "UNAVAILABLE" in error_text
            ):
                print(
                    f"MyAI temporary overload on {model}. "
                    "Trying next model."
                )
                continue

            if (
                "404" in error_text
                or "NOT_FOUND" in error_text
            ):
                print(
                    f"MyAI model {model} unavailable. "
                    "Trying next model."
                )
                continue

            print(
                f"MyAI error on {model}. "
                "Trying next model."
            )

            continue

    return jsonify({
        "error": (
            "MyAI could not get a response from "
            "any available Gemini model. "
            f"Last error: {last_error}"
        )
    }), 503
