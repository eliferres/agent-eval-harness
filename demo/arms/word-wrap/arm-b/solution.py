def wrap(text, width):
    """Greedy word wrap. See SPEC.md for the rules this implements."""
    if width < 1:
        raise ValueError("width must be positive")

    chunks = []
    for word in text.split():
        while len(word) > width:
            chunks.append(word[:width])
            word = word[width:]
        if word:
            chunks.append(word)

    lines = []
    for chunk in chunks:
        if lines and len(lines[-1]) + 1 + len(chunk) <= width:
            lines[-1] += " " + chunk
        else:
            lines.append(chunk)
    return lines
