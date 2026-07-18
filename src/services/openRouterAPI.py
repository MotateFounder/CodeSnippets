import json
import urllib.error
import urllib.request

def build_openrouter_payload(messages, stream=True, model="", temperature=0.2, max_tokens=0):
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "stream": stream,
    }
    if max_tokens:
        payload["max_tokens"] = max_tokens
    return payload


def build_openrouter_headers(api_key="", app_title=""):
    if not api_key:
        raise ValueError("OpenRouter API key is missing. Add it in Settings.")
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
        "X-Title": app_title,
    }


def stream_openrouter_chat(messages, on_chunk=None, timeout=180, settings=None):
    settings = settings or {}
    openrouter = settings.get("openrouter", {})
    generation = settings.get("generation", {})
    endpoint = openrouter.get("endpoint", "").strip()
    model = openrouter.get("model", "").strip()
    if not endpoint:
        raise ValueError("OpenRouter endpoint is missing. Add it in Settings.")
    if not model:
        raise ValueError("OpenRouter model is missing. Add it in Settings.")
    payload = build_openrouter_payload(
        messages,
        stream=True,
        model=model,
        temperature=float(generation.get("temperature", 0.2)),
        max_tokens=int(generation.get("max_tokens", 0) or 0),
    )
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=data,
        headers=build_openrouter_headers(
            api_key=openrouter.get("api_key", "").strip(),
            app_title=openrouter.get("app_title", "").strip(),
        ),
        method="POST",
    )

    with urllib.request.urlopen(request, timeout=timeout) as response:
        return read_openrouter_stream(response, on_chunk=on_chunk)


def call_openrouter_chat(messages, timeout=180, settings=None):
    settings = settings or {}
    openrouter = settings.get("openrouter", {})
    generation = settings.get("generation", {})
    endpoint = openrouter.get("endpoint", "").strip()
    model = openrouter.get("model", "").strip()
    if not endpoint:
        raise ValueError("OpenRouter endpoint is missing. Add it in Settings.")
    if not model:
        raise ValueError("OpenRouter model is missing. Add it in Settings.")
    payload = build_openrouter_payload(
        messages,
        stream=False,
        model=model,
        temperature=float(generation.get("reasoning_temperature", 0.1)),
        max_tokens=int(generation.get("max_tokens", 0) or 0),
    )
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=data,
        headers=build_openrouter_headers(
            api_key=openrouter.get("api_key", "").strip(),
            app_title=openrouter.get("app_title", "").strip(),
        ),
        method="POST",
    )

    with urllib.request.urlopen(request, timeout=timeout) as response:
        parsed = json.loads(response.read().decode("utf-8", errors="replace"))
    return extract_openrouter_answer(parsed)


def read_openrouter_stream(response, on_chunk=None):
    answer_parts = []
    raw_lines = []

    for raw_line in response:
        line = raw_line.decode("utf-8", errors="replace").strip()
        if not line:
            continue

        if not line.startswith("data:"):
            raw_lines.append(line)
            continue

        data = line[5:].strip()
        if data == "[DONE]":
            break

        parsed = json.loads(data)
        chunk = extract_openrouter_delta(parsed)
        if chunk:
            answer_parts.append(chunk)
            if on_chunk:
                on_chunk(chunk)

    if answer_parts:
        return "".join(answer_parts)

    raw_response = "\n".join(raw_lines).strip()
    if raw_response:
        parsed = json.loads(raw_response)
        answer = extract_openrouter_answer(parsed)
        if answer and on_chunk:
            on_chunk(answer)
        return answer

    return ""


def extract_openrouter_delta(parsed):
    choices = parsed.get("choices", [])
    if not choices:
        return ""
    delta = choices[0].get("delta", {})
    content = delta.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(part.get("text", "") for part in content if isinstance(part, dict))
    return ""


def extract_openrouter_answer(parsed):
    choices = parsed.get("choices", [])
    if not choices:
        return ""
    message = choices[0].get("message", {})
    content = message.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(part.get("text", "") for part in content if isinstance(part, dict))
    return ""


def openrouter_error_message(exc):
    if isinstance(exc, urllib.error.HTTPError):
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except OSError:
            body = ""
        if body:
            return f"{exc.code} {exc.reason}: {body}"
        return f"{exc.code} {exc.reason}"
    return str(exc)
