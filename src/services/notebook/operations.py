from datetime import datetime
from copy import deepcopy
from uuid import uuid4


NOTEBOOK_COLORS = [
    "#7c83ff",
    "#ff8a4c",
    "#6f45b8",
    "#e53048",
    "#14a8d4",
    "#2fbfaa",
    "#d891ef",
    "#88a344",
]


def timestamp():
    return datetime.now().isoformat(timespec="seconds")


def new_id():
    return uuid4().hex[:12]


def display_datetime(value):
    try:
        dt = datetime.fromisoformat(str(value))
    except ValueError:
        dt = datetime.now()
    return dt.strftime("%A, %B %d, %Y   %I:%M%p").replace(" 0", " ")


def new_notebook(name, color=None):
    now = timestamp()
    return {
        "id": new_id(),
        "name": str(name or "Untitled Notebook").strip() or "Untitled Notebook",
        "color": color or NOTEBOOK_COLORS[0],
        "createdAt": now,
        "updatedAt": now,
        "pages": [],
    }


def new_page(title="Untitled Page"):
    now = timestamp()
    return {
        "id": new_id(),
        "title": str(title or "Untitled Page").strip() or "Untitled Page",
        "content": "",
        "tags": [],
        "createdAt": now,
        "updatedAt": now,
    }


def ensure_sample_data(data):
    if data.get("notebooks"):
        return data
    notebook = new_notebook("Work Notebook", NOTEBOOK_COLORS[1])
    page = new_page("Terms and conditions")
    page["content"] = "Start writing here."
    notebook["pages"].append(page)
    data["notebooks"] = [notebook]
    data["selectedNotebookId"] = notebook["id"]
    data["selectedPageId"] = page["id"]
    return data


def notebook_by_id(data, notebook_id):
    for notebook in data.get("notebooks", []):
        if notebook.get("id") == notebook_id:
            return notebook
    return None


def page_by_id(notebook, page_id):
    for page in notebook.get("pages", []):
        if page.get("id") == page_id:
            return page
    return None


def selected_notebook(data):
    notebook = notebook_by_id(data, data.get("selectedNotebookId", ""))
    if notebook:
        return notebook
    notebooks = data.get("notebooks", [])
    if notebooks:
        data["selectedNotebookId"] = notebooks[0]["id"]
        return notebooks[0]
    return None


def selected_page(data):
    notebook = selected_notebook(data)
    if not notebook:
        return None
    page = page_by_id(notebook, data.get("selectedPageId", ""))
    if page:
        return page
    pages = notebook.get("pages", [])
    if pages:
        data["selectedPageId"] = pages[0]["id"]
        return pages[0]
    return None


def add_notebook(data, name):
    color = NOTEBOOK_COLORS[len(data.get("notebooks", [])) % len(NOTEBOOK_COLORS)]
    notebook = new_notebook(name, color)
    page = new_page("Untitled Page")
    notebook["pages"].append(page)
    data.setdefault("notebooks", []).append(notebook)
    data["selectedNotebookId"] = notebook["id"]
    data["selectedPageId"] = page["id"]
    return notebook


def add_page(data, title):
    notebook = selected_notebook(data)
    if not notebook:
        notebook = add_notebook(data, "Untitled Notebook")
    page = new_page(title)
    notebook.setdefault("pages", []).append(page)
    notebook["updatedAt"] = timestamp()
    data["selectedNotebookId"] = notebook["id"]
    data["selectedPageId"] = page["id"]
    return page


def duplicate_notebook(data, notebook_id):
    source = notebook_by_id(data, notebook_id)
    if not source:
        return None
    now = timestamp()
    notebook = deepcopy(source)
    notebook["id"] = new_id()
    notebook["name"] = "{0} Copy".format(source.get("name", "Untitled Notebook"))
    notebook["createdAt"] = now
    notebook["updatedAt"] = now
    for page in notebook.get("pages", []):
        page["id"] = new_id()
        page["createdAt"] = now
        page["updatedAt"] = now
    data.setdefault("notebooks", []).append(notebook)
    data["selectedNotebookId"] = notebook["id"]
    data["selectedPageId"] = notebook["pages"][0]["id"] if notebook.get("pages") else ""
    return notebook


def duplicate_page(data, page_id):
    notebook = selected_notebook(data)
    if not notebook:
        return None
    source = page_by_id(notebook, page_id)
    if not source:
        return None
    page = deepcopy(source)
    page["id"] = new_id()
    page["title"] = "{0} Copy".format(source.get("title", "Untitled Page"))
    page["createdAt"] = timestamp()
    page["updatedAt"] = page["createdAt"]
    notebook.setdefault("pages", []).append(page)
    notebook["updatedAt"] = timestamp()
    data["selectedPageId"] = page["id"]
    return page


def rename_notebook(notebook, name):
    notebook["name"] = str(name or "Untitled Notebook").strip() or "Untitled Notebook"
    notebook["updatedAt"] = timestamp()


def rename_page(page, title):
    page["title"] = str(title or "Untitled Page").strip() or "Untitled Page"
    page["updatedAt"] = timestamp()


def delete_notebook(data, notebook_id):
    data["notebooks"] = [item for item in data.get("notebooks", []) if item.get("id") != notebook_id]
    first = data["notebooks"][0] if data["notebooks"] else None
    data["selectedNotebookId"] = first["id"] if first else ""
    data["selectedPageId"] = first["pages"][0]["id"] if first and first.get("pages") else ""


def delete_page(data, page_id):
    notebook = selected_notebook(data)
    if not notebook:
        return
    notebook["pages"] = [item for item in notebook.get("pages", []) if item.get("id") != page_id]
    notebook["updatedAt"] = timestamp()
    first = notebook["pages"][0] if notebook.get("pages") else None
    data["selectedPageId"] = first["id"] if first else ""


def filter_pages(notebook, query):
    query = str(query or "").strip().lower()
    pages = list(notebook.get("pages", [])) if notebook else []
    if not query:
        return pages
    result = []
    for page in pages:
        haystack = "{0}\n{1}\n{2}".format(
            page.get("title", ""),
            page.get("content", ""),
            " ".join(page.get("tags", [])),
        ).lower()
        if query in haystack:
            result.append(page)
    return result


def update_page_content(page, title, content, spans=None):
    next_title = str(title or "Untitled Page").strip() or "Untitled Page"
    next_content = str(content or "")
    next_spans = list(spans or [])
    if (
        page.get("title") == next_title
        and page.get("content", "") == next_content
        and page.get("spans", []) == next_spans
    ):
        return False
    page["title"] = next_title
    page["content"] = next_content
    page["spans"] = next_spans
    page["updatedAt"] = timestamp()
    return True
