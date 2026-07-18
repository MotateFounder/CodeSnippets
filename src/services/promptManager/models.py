from copy import deepcopy
from datetime import datetime
from uuid import uuid4


DEFAULT_NOTEBOOKS = [
    ("Coding", "Refactor safely", "Refactor {{file}} without changing [behaviour]."),
    ("Debugging", "Explain a failure", "Diagnose [error] using {{code_context}}."),
    ("Documentation", "Write docs", "Write documentation for [feature] using {{code_context}}."),
]


def timestamp():
    return datetime.now().isoformat(timespec="seconds")


def new_id():
    return uuid4().hex[:12]


def new_prompt(name="Untitled Prompt", text=""):
    now = timestamp()
    return {
        "id": new_id(),
        "name": str(name or "Untitled Prompt").strip() or "Untitled Prompt",
        "text": str(text or ""),
        "variables": {},
        "createdAt": now,
        "updatedAt": now,
    }


def new_notebook(name="Untitled Notebook"):
    now = timestamp()
    return {
        "id": new_id(),
        "name": str(name or "Untitled Notebook").strip() or "Untitled Notebook",
        "createdAt": now,
        "updatedAt": now,
        "prompts": [],
    }


def normalize_prompt(prompt):
    if not isinstance(prompt, dict):
        prompt = {}
    created = str(prompt.get("createdAt", "") or timestamp())
    variables = prompt.get("variables", {})
    if not isinstance(variables, dict):
        variables = {}
    return {
        "id": str(prompt.get("id", "") or "").strip() or new_id(),
        "name": str(prompt.get("name", "") or "Untitled Prompt").strip() or "Untitled Prompt",
        "text": str(prompt.get("text", "") or ""),
        "variables": {str(key): str(value or "") for key, value in variables.items()},
        "createdAt": created,
        "updatedAt": str(prompt.get("updatedAt", "") or created),
    }


def normalize_notebook(notebook):
    if not isinstance(notebook, dict):
        notebook = {}
    prompts = []
    seen = set()
    for raw in notebook.get("prompts", []):
        prompt = normalize_prompt(raw)
        if prompt["id"] in seen:
            prompt["id"] = new_id()
        seen.add(prompt["id"])
        prompts.append(prompt)
    created = str(notebook.get("createdAt", "") or timestamp())
    return {
        "id": str(notebook.get("id", "") or "").strip() or new_id(),
        "name": str(notebook.get("name", "") or "Untitled Notebook").strip() or "Untitled Notebook",
        "createdAt": created,
        "updatedAt": str(notebook.get("updatedAt", "") or created),
        "prompts": prompts,
    }


def normalize_data(data):
    if not isinstance(data, dict):
        data = {}
    notebooks = []
    seen = set()
    for raw in data.get("notebooks", []):
        notebook = normalize_notebook(raw)
        if notebook["id"] in seen:
            notebook["id"] = new_id()
        seen.add(notebook["id"])
        notebooks.append(notebook)
    normalized = {
        "version": 1,
        "selectedNotebookId": str(data.get("selectedNotebookId", "") or ""),
        "selectedPromptId": str(data.get("selectedPromptId", "") or ""),
        "notebooks": notebooks,
    }
    return ensure_selection(ensure_sample_data(normalized))


def ensure_sample_data(data):
    if data.get("notebooks"):
        return data
    notebooks = []
    for notebook_name, prompt_name, prompt_text in DEFAULT_NOTEBOOKS:
        notebook = new_notebook(notebook_name)
        notebook["prompts"].append(new_prompt(prompt_name, prompt_text))
        notebooks.append(notebook)
    data["notebooks"] = notebooks
    data["selectedNotebookId"] = notebooks[0]["id"]
    data["selectedPromptId"] = notebooks[0]["prompts"][0]["id"]
    return data


def ensure_selection(data):
    notebooks = data.get("notebooks", [])
    notebook_ids = [notebook["id"] for notebook in notebooks]
    if notebooks and data.get("selectedNotebookId") not in notebook_ids:
        data["selectedNotebookId"] = notebooks[0]["id"]
    notebook = selected_notebook(data)
    if notebook:
        prompt_ids = [prompt["id"] for prompt in notebook.get("prompts", [])]
        if prompt_ids and data.get("selectedPromptId") not in prompt_ids:
            data["selectedPromptId"] = prompt_ids[0]
        if not prompt_ids:
            data["selectedPromptId"] = ""
    else:
        data["selectedNotebookId"] = ""
        data["selectedPromptId"] = ""
    return data


def selected_notebook(data):
    return notebook_by_id(data, data.get("selectedNotebookId", ""))


def selected_prompt(data):
    notebook = selected_notebook(data)
    if not notebook:
        return None
    return prompt_by_id(notebook, data.get("selectedPromptId", ""))


def notebook_by_id(data, notebook_id):
    for notebook in data.get("notebooks", []):
        if notebook.get("id") == notebook_id:
            return notebook
    return None


def prompt_by_id(notebook, prompt_id):
    for prompt in notebook.get("prompts", []):
        if prompt.get("id") == prompt_id:
            return prompt
    return None


def add_notebook(data, name):
    notebook = new_notebook(name)
    notebook["prompts"].append(new_prompt())
    data.setdefault("notebooks", []).append(notebook)
    data["selectedNotebookId"] = notebook["id"]
    data["selectedPromptId"] = notebook["prompts"][0]["id"]
    return notebook


def rename_notebook(notebook, name):
    notebook["name"] = str(name or "Untitled Notebook").strip() or "Untitled Notebook"
    notebook["updatedAt"] = timestamp()


def delete_notebook(data, notebook_id):
    data["notebooks"] = [item for item in data.get("notebooks", []) if item.get("id") != notebook_id]
    ensure_selection(data)


def add_prompt(data, name="Untitled Prompt"):
    notebook = selected_notebook(data)
    if not notebook:
        notebook = add_notebook(data, "Untitled Notebook")
    prompt = new_prompt(name)
    notebook.setdefault("prompts", []).append(prompt)
    notebook["updatedAt"] = timestamp()
    data["selectedPromptId"] = prompt["id"]
    return prompt


def rename_prompt(prompt, name):
    prompt["name"] = str(name or "Untitled Prompt").strip() or "Untitled Prompt"
    prompt["updatedAt"] = timestamp()


def duplicate_prompt(data, prompt_id):
    notebook = selected_notebook(data)
    if not notebook:
        return None
    source = prompt_by_id(notebook, prompt_id)
    if not source:
        return None
    prompt = deepcopy(source)
    now = timestamp()
    prompt["id"] = new_id()
    prompt["name"] = "{0} Copy".format(source.get("name", "Untitled Prompt"))
    prompt["createdAt"] = now
    prompt["updatedAt"] = now
    notebook.setdefault("prompts", []).append(prompt)
    notebook["updatedAt"] = now
    data["selectedPromptId"] = prompt["id"]
    return prompt


def delete_prompt(data, prompt_id):
    notebook = selected_notebook(data)
    if not notebook:
        return
    notebook["prompts"] = [item for item in notebook.get("prompts", []) if item.get("id") != prompt_id]
    notebook["updatedAt"] = timestamp()
    ensure_selection(data)


def update_prompt(prompt, name, text, variables):
    next_name = str(name or "Untitled Prompt").strip() or "Untitled Prompt"
    next_text = str(text or "")
    next_variables = {str(key): str(value or "") for key, value in (variables or {}).items()}
    if prompt.get("name") == next_name and prompt.get("text", "") == next_text and prompt.get("variables", {}) == next_variables:
        return False
    prompt["name"] = next_name
    prompt["text"] = next_text
    prompt["variables"] = next_variables
    prompt["updatedAt"] = timestamp()
    return True


def filter_prompts(notebook, query):
    prompts = list(notebook.get("prompts", [])) if notebook else []
    query = str(query or "").strip().lower()
    if not query:
        return prompts
    result = []
    for prompt in prompts:
        haystack = "{0}\n{1}".format(prompt.get("name", ""), prompt.get("text", "")).lower()
        if query in haystack:
            result.append(prompt)
    return result

