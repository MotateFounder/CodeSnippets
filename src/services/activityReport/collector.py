from datetime import datetime


def parse_stored_timestamp(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def in_range(value, start, end):
    parsed = parse_stored_timestamp(value)
    return bool(parsed and start <= parsed <= end)


def collect_activity_entries(notebook_data, chat_threads, start, end):
    entries = []
    warnings = []
    entries.extend(collect_note_entries(notebook_data or {}, start, end, warnings))
    entries.extend(collect_chat_entries(chat_threads or [], start, end, warnings))
    entries.sort(key=lambda item: item["timestamp"])
    return entries, warnings


def collect_note_entries(notebook_data, start, end, warnings):
    entries = []
    for notebook in notebook_data.get("notebooks", []):
        notebook_name = notebook.get("name", "Untitled Notebook")
        for page in notebook.get("pages", []):
            created = page.get("createdAt", "")
            updated = page.get("updatedAt", "")
            created_dt = parse_stored_timestamp(created)
            updated_dt = parse_stored_timestamp(updated)
            if created and not created_dt:
                warnings.append("Invalid note created timestamp: {0}".format(page.get("title", "Untitled Page")))
            if updated and not updated_dt:
                warnings.append("Invalid note updated timestamp: {0}".format(page.get("title", "Untitled Page")))
            selected_dt = None
            if updated_dt and start <= updated_dt <= end:
                selected_dt = updated_dt
            elif created_dt and start <= created_dt <= end:
                selected_dt = created_dt
            if not selected_dt:
                continue
            text = str(page.get("content", "") or "").strip()
            title = str(page.get("title", "Untitled Page") or "Untitled Page")
            if not text and not title.strip():
                continue
            entries.append(
                {
                    "timestamp": selected_dt,
                    "source_type": "note",
                    "title": title,
                    "text": text,
                    "metadata": {
                        "notebook": notebook_name,
                        "createdAt": created,
                        "updatedAt": updated,
                    },
                }
            )
    return entries


def collect_chat_entries(chat_threads, start, end, warnings):
    entries = []
    for thread_index, thread in enumerate(chat_threads):
        thread_title = thread.get("title", "Chat {0}".format(thread_index + 1))
        for message_index, message in enumerate(thread.get("messages", [])):
            role = message.get("role", "")
            if role not in {"user", "assistant"}:
                continue
            created = message.get("created_at", "")
            created_dt = parse_stored_timestamp(created)
            if created and not created_dt:
                warnings.append("Invalid chat timestamp in {0}.".format(thread_title))
            if not created_dt or not (start <= created_dt <= end):
                continue
            content = str(message.get("content", "") or "").strip()
            if not content:
                continue
            entries.append(
                {
                    "timestamp": created_dt,
                    "source_type": "user message" if role == "user" else "assistant message",
                    "title": thread_title,
                    "text": content,
                    "metadata": {
                        "thread": thread_title,
                        "threadIndex": thread_index,
                        "messageIndex": message_index,
                    },
                }
            )
    return entries

