"""Select approval references from an already validated, tenant-bound policy revision."""
import re


def source_role(article):
    doc = article.split(" | ", 1)[0].split(" ", 1)[0]
    if re.fullmatch(r"POL-\d+", doc):
        return "COMPANY_POLICY"
    if "-OFF-" in doc:
        return "PRODUCT_REFERENCE"
    if doc == "FLOW":
        return "COMPANY_WORKFLOW"
    return "IMPLEMENTATION_SCOPE"


def approval_evidence(evidence, platform, kind=None, access_scope=None):
    """Exact reads ensure coverage; retrieval order alone must not decide mandatory rules.

    Official references explain a capability, not the requester's eligibility or price.
    Historical baseline-v1 headings remain supported without rewriting their revision.
    """
    selected = []
    for item in evidence:
        article = item["article"]
        fields = article.split(" | ")
        if len(fields) == 4 and fields[1] not in {"COMMON", platform}:
            continue
        if (article.startswith("POL-06") and "제5조" in article
                or article.startswith("POL-02") and "제4조" in article
                or article.startswith("BASELINE") and "회수" in article):
            continue
        if access_scope and access_scope != "TF" and article.startswith("POL-02"):
            continue
        if platform == "GITHUB" and kind:
            if kind == "SEAT" and article.startswith(("POL-03", "GH-OFF-01", "GH-OFF-02")):
                continue
            if kind != "SEAT" and article.startswith("GH-OFF-03"):
                continue
        selected.append(item)
    return selected
