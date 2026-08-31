def wrap(text, width):
    """Greedy word wrap. See SPEC.md for the rules this implements."""
    if width < 1:
        raise ValueError("Expected `width` to be at least 1, got `%r`" % width)

    lines = []
    line = ""
    for word in text.split():
        if not line:
            # An over-long word starts its own line and, being over-long,
            # never leaves room for a second - so rule 3 needs no branch.
            line = word
        elif len(line) + 1 + len(word) <= width:
            line += " " + word
        else:
            lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines
