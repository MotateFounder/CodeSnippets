from pathlib import Path


def report_filename(start, end):
    return "CodeSnippets_Report_{0}_to_{1}.txt".format(
        start.strftime("%Y-%m-%d"),
        end.strftime("%Y-%m-%d"),
    )


def unique_report_path(folder, start, end):
    folder = Path(folder)
    base = folder / report_filename(start, end)
    if not base.exists():
        return base
    stem = base.stem
    suffix = base.suffix
    counter = 2
    while True:
        candidate = folder / "{0}_{1}{2}".format(stem, counter, suffix)
        if not candidate.exists():
            return candidate
        counter += 1


def save_report(folder, start, end, text):
    path = unique_report_path(folder, start, end)
    path.write_text(str(text or ""), encoding="utf-8")
    return path

