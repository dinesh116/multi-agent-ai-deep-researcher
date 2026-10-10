"""Results tab: Full report, with references and citation traceability checks."""
from html import escape

import pandas as pd
import streamlit as st

from src.models.run import RunBundle
from src.ui.components import card, html


def render(bundle: RunBundle) -> None:
    report = bundle.report
    with card("report"):
        html(f'<div class="ds-label">Full research report</div><div style="font:700 21px/1.4 Manrope,sans-serif;'
             f'margin:10px 0 4px">{escape(report.title)}</div>')
        st.caption(f"Generated {report.created_at:%d %b %Y %H:%M} · {report.generated_by} · "
                   f"{len(report.references)} references")
        with st.expander("Contents"):
            st.markdown("\n".join(f"{i}. {s.title}" for i, s in enumerate(report.sections, start=1)))
        for section in report.sections:
            st.markdown(f"#### {section.title}")
            if section.key == "references":
                for r in report.references:
                    line = f"**[{r['n']}]** {r['label']}"
                    if r.get("url"):
                        line += f" · [{'link (synthetic)' if r['synthetic'] else 'link'}]({r['url']})"
                    tags = [r["origin_label"]] + ([] if r["full_text_reviewed"] else ["abstract/snippet only"])
                    st.markdown(line + f"  \n<span class='dr-muted'>{' · '.join(tags)}</span>", unsafe_allow_html=True)
            else:
                st.markdown(section.content)

    checks = report.citation_checks
    with st.expander(f"Citation traceability: {sum(c.valid for c in checks)}/{len(checks)} citations passed"):
        st.caption("Checks that each cited source exists in the corpus, that the reference entry matches the source "
                   "record, that the cited passage is relevant to the sentence, and that the citation renders. "
                   "Traceability does **not** establish that a claim is true.")
        if checks:
            st.dataframe(pd.DataFrame([{"Marker": c.marker, "Source exists": c.exists,
                                        "Reference matches": c.reference_matches, "Passage relevant": c.passage_relevant,
                                        "Renders": c.renderable, "Note": c.note} for c in checks]),
                         hide_index=True, width="stretch")
