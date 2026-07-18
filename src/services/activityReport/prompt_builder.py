DEFAULT_REPORT_TEMPLATE = """Analyze the supplied CodeSnippets activity evidence and write a useful work report.

Goal:
Describe what work was actually performed during the selected period.

Rules:
* Plain text only.
* Group work by calendar day when there is enough activity.
* Use at most [[bullet_limit]] bullet point(s) per day or section.
* Each bullet must be short, concrete, and useful.
* Prefer task-level descriptions such as "Improved report generation" instead of restating chat messages.
* Merge repeated or closely related activity into one bullet.
* Mention specific files, features, or decisions only when they are clearly meaningful.
* Ignore greetings, explanations about the process, temporary status updates, and side discussion.
* Do not invent work, dates, results, decisions, or missing context.
* [[summary_instruction]]

Selected range:
[[selected_range]]

Output format:
Monday, 12 July 2026
* Bullet 1
* Bullet 2
* Bullet 3"""


def build_report_messages(entries, start, end, bullet_limit, include_summary, template=None):
    content = build_report_prompt(entries, start, end, bullet_limit, include_summary, template=template)
    return [
        {
            "role": "system",
            "content": (
                "You write concise factual activity reports. Focus on work performed and tasks completed, "
                "not on the conversation mechanics. Use only the supplied source entries."
            ),
        },
        {"role": "user", "content": content},
    ]


def build_report_prompt(entries, start, end, bullet_limit, include_summary, template=None):
    prompt = render_report_template(
        template or DEFAULT_REPORT_TEMPLATE,
        start,
        end,
        bullet_limit,
        include_summary,
        entry_count=len(entries),
    )
    evidence = build_evidence_block(entries)
    return "{0}\n\n{1}".format(prompt.strip(), evidence).strip()


def render_report_template(template, start, end, bullet_limit, include_summary, entry_count=0):
    summary_instruction = (
        "After the bullets, add a short Summary section."
        if include_summary
        else "Do not add a Summary section."
    )
    selected_range = "Start: {0}\nEnd: {1}".format(
        start.isoformat(timespec="seconds"),
        end.isoformat(timespec="seconds"),
    )
    return (
        str(template or "")
        .replace("[[bullet_limit]]", str(bullet_limit))
        .replace("[[summary_instruction]]", summary_instruction)
        .replace("[[selected_range]]", selected_range)
        .replace("[[entry_count]]", str(entry_count))
    )


def build_evidence_block(entries):
    lines = [
        "===== BEGIN HIDDEN ACTIVITY EVIDENCE =====",
        "Entry count: {0}".format(len(entries)),
        "Evidence entries, chronological order:",
        "Use these only as evidence of work performed.",
        "Extract completed changes, implementation work, design decisions, and useful outcomes.",
        "Do not summarize the conversation itself unless the conversation directly records work performed.",
    ]
    for index, entry in enumerate(entries, start=1):
        lines.extend(format_entry(index, entry))
    lines.append("===== END HIDDEN ACTIVITY EVIDENCE =====")
    return "\n".join(lines).strip()


def format_entry(index, entry):
    metadata = entry.get("metadata", {}) or {}
    metadata_text = "; ".join(
        "{0}={1}".format(key, value)
        for key, value in metadata.items()
        if value not in {None, ""}
    )
    lines = [
        "",
        "Entry {0}".format(index),
        "Timestamp: {0}".format(entry["timestamp"].isoformat(timespec="seconds")),
        "Type: {0}".format(entry.get("source_type", "")),
        "Title: {0}".format(entry.get("title", "")),
    ]
    if metadata_text:
        lines.append("Metadata: {0}".format(metadata_text))
    lines.extend(["Text:", str(entry.get("text", "")).strip()])
    return lines
