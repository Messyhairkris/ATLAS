KINDS = ("code", "comment", "string", "template", "regex")


def segments(source: str) -> list[tuple[str, str]]:
    i = 0
    n = len(source)
    segments_list = []
    code_buf = []

    while i < n:
        # Check for line comment
        if i + 1 < n and source[i : i + 2] == "//":
            if code_buf:
                segments_list.append(("code", "".join(code_buf)))
                code_buf = []
            j = i + 2
            while j < n and source[j] != "\n":
                j += 1
            comment_text = source[i:j]
            segments_list.append(("comment", comment_text))
            i = j
            continue

        # Check for block comment
        if i + 1 < n and source[i : i + 2] == "/*":
            if code_buf:
                segments_list.append(("code", "".join(code_buf)))
                code_buf = []
            j = i + 2
            while j < n:
                if j + 1 < n and source[j : j + 2] == "*/":
                    j += 2
                    break
                j += 1
            comment_text = source[i:j]
            segments_list.append(("comment", comment_text))
            i = j
            continue

        # Check for string
        if source[i] in "\"'":
            if code_buf:
                segments_list.append(("code", "".join(code_buf)))
                code_buf = []
            quote = source[i]
            j = i + 1
            escaped = False
            while j < n:
                c = source[j]
                if escaped:
                    escaped = False
                elif c == "\\":
                    escaped = True
                elif c == quote:
                    break
                j += 1
            j += 1  # include the closing quote
            string_text = source[i:j]
            segments_list.append(("string", string_text))
            i = j
            continue

        # Check for template
        if source[i] == "`":
            if code_buf:
                segments_list.append(("code", "".join(code_buf)))
                code_buf = []
            j = i + 1
            escaped = False
            while j < n:
                c = source[j]
                if escaped:
                    escaped = False
                elif c == "\\":
                    escaped = True
                elif c == "`":
                    break
                j += 1
            j += 1  # include the closing backtick
            template_text = source[i:j]
            segments_list.append(("template", template_text))
            i = j
            continue

        # Check for regex: only if it's a '/'
        if source[i] == "/":
            # Check position condition: code before (ignoring comments and trailing whitespace) is empty, ends with certain chars, or ends with certain words
            non_comment_parts = []
            for kind, text in segments_list:
                if kind != "comment":
                    non_comment_parts.append(text)
            non_comment_parts.append("".join(code_buf))
            full_text = "".join(non_comment_parts)
            cleaned = full_text.rstrip()

            pos_ok = False
            if cleaned == "":
                pos_ok = True
            else:
                last_char = cleaned[-1]
                if last_char in "(),=:[!&|?{};+-*/%<>~^":
                    pos_ok = True
                else:
                    words = [
                        "return",
                        "typeof",
                        "instanceof",
                        "in",
                        "of",
                        "new",
                        "delete",
                        "void",
                        "throw",
                        "case",
                        "do",
                        "else",
                        "yield",
                        "await",
                    ]
                    for word in words:
                        if cleaned.endswith(word):
                            if len(cleaned) == len(word):
                                pos_ok = True
                                break
                            prev_char = cleaned[len(cleaned) - len(word) - 1]
                            if not (prev_char.isalnum() or prev_char in "_$"):
                                pos_ok = True
                                break

            if pos_ok:
                j = i + 1
                in_class = False
                escaped = False
                regex_end = -1
                newline_seen = False
                while j < n:
                    c = source[j]
                    if c == "\n":
                        newline_seen = True
                        break
                    if escaped:
                        escaped = False
                    else:
                        if c == "\\":
                            escaped = True
                        elif c == "[":
                            in_class = True
                        elif c == "]":
                            in_class = False
                        elif c == "/" and not in_class:
                            regex_end = j
                            break
                    j += 1

                if regex_end != -1 and not newline_seen:
                    k = regex_end + 1
                    while k < n and source[k].isalpha():
                        k += 1
                    regex_text = source[i:k]
                    if code_buf:
                        segments_list.append(("code", "".join(code_buf)))
                        code_buf = []
                    segments_list.append(("regex", regex_text))
                    i = k
                    continue

            # If not regex, fall through to treat as normal character

        # Any other character (including '/' that is not a regex) is code
        code_buf.append(source[i])
        i += 1

    if code_buf:
        segments_list.append(("code", "".join(code_buf)))

    return segments_list


def code_only(source: str) -> str:
    segs = segments(source)
    parts = []
    for kind, text in segs:
        if kind == "comment":
            parts.append(" ")
        elif kind == "string":
            parts.append('""')
        elif kind == "template":
            parts.append("``")
        elif kind == "regex":
            parts.append("/_/")
        else:  # code
            parts.append(text)
    return "".join(parts)
