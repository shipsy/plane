# Third party imports
import nh3

# Tags and attributes produced by the rich text editor (packages/editor).
# Anything else, including scripts, iframes, event handlers and javascript:
# URLs, is removed before the HTML is stored.
ALLOWED_TAGS = {
    "p", "br", "strong", "b", "em", "i", "u", "s", "strike",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "ul", "ol", "li", "blockquote", "hr", "pre", "code", "a", "span",
    "div", "label", "input",
    "table", "thead", "tbody", "tr", "td", "th", "colgroup", "col",
    "img", "image-component", "mention-component", "issue-embed-component",
}

TABLE_CELL_ATTRIBUTES = {
    "colspan", "rowspan", "colwidth", "background", "textcolor", "textColor",
}

IMAGE_ATTRIBUTES = {
    "src", "alt", "title", "width", "height", "aspectratio", "aspectRatio",
}

ALLOWED_ATTRIBUTES = {
    "*": {"class", "style"},
    "ol": {"start"},
    "a": {"href", "target"},
    "input": {"type", "checked", "disabled"},
    "tr": {"background", "textcolor", "textColor"},
    "td": TABLE_CELL_ATTRIBUTES,
    "th": TABLE_CELL_ATTRIBUTES,
    "img": IMAGE_ATTRIBUTES,
    "image-component": IMAGE_ATTRIBUTES | {"id"},
    "mention-component": {
        "id", "label", "target", "self", "redirect_uri",
        "entity_identifier", "entity_name",
    },
    "issue-embed-component": {
        "id", "entity_identifier", "entity_name",
        "project_identifier", "workspace_identifier",
    },
}

# Only the inline styles the editor writes (text/table colors, sizes)
ALLOWED_STYLE_PROPERTIES = {"color", "background-color", "width", "height"}


def sanitize_html(value):
    """Return editor HTML with everything outside the allowlist removed"""
    if not value:
        return value
    return nh3.clean(
        str(value),
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        # data-* carries task list, color and callout state
        generic_attribute_prefixes={"data-"},
        url_schemes={"http", "https", "mailto"},
        filter_style_properties=ALLOWED_STYLE_PROPERTIES,
        link_rel="noopener noreferrer nofollow",
    )
